"""Built-in evidence exporters (``aegis.exporters`` entry points).

Configured under ``exporters:`` in ``aegis.yaml``; every record appended to
the evidence ledger is also delivered to each exporter::

    exporters:
      archive:
        type: jsonl
        path: /var/log/aegis/evidence.jsonl
      siem:
        type: webhook
        url: https://siem.example.com/ingest/aegis
        headers:
          Authorization: secret://env/SIEM_TOKEN#value
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from aegis_core.packs import ExporterConfig


def _required(cfg: ExporterConfig, name: str, field: str) -> Any:
    value = getattr(cfg, field, None)
    if not value:
        from aegis_core.errors import AegisConfigValidationError

        raise AegisConfigValidationError(
            f"exporters.{name} (type {cfg.type!r}) requires {field!r}.", exporter=name
        )
    return value


def _plain(value: Any) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else str(value)


class JsonlExporter:
    """Appends each record as one JSON line to a local file (e.g. for log shipping)."""

    def __init__(self, path: str | Path, name: str = "jsonl") -> None:
        self.name = name
        self._path = Path(path)

    @classmethod
    def from_config(cls, name: str, cfg: ExporterConfig) -> JsonlExporter:
        return cls(path=_required(cfg, name, "path"), name=name)

    async def export(self, records: list[dict]) -> None:
        if not records:
            return
        lines = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records)

        def _write() -> None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(lines)

        await asyncio.to_thread(_write)


class WebhookExporter:
    """POSTs records as JSON (``{"records": [...]}``) to an HTTP endpoint.

    Options: ``url`` (required), ``headers`` (values may be ``secret://`` refs),
    ``timeout`` in seconds (default 10). Non-2xx responses raise, which the
    ledger's forwarding worker logs and counts.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
        name: str = "webhook",
        transport: Any | None = None,
    ) -> None:
        self.name = name
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout
        self._transport = transport  # httpx transport override, for tests

    @classmethod
    def from_config(cls, name: str, cfg: ExporterConfig) -> WebhookExporter:
        headers = getattr(cfg, "headers", None) or {}
        return cls(
            url=_plain(_required(cfg, name, "url")),
            headers={str(k): _plain(v) for k, v in dict(headers).items()},
            timeout=float(getattr(cfg, "timeout", 10.0)),
            name=name,
        )

    async def export(self, records: list[dict]) -> None:
        if not records:
            return
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self._url, json={"records": records}, headers=self._headers)
            response.raise_for_status()
