"""Evidence exporters: built-ins, the forwarding ledger, and config wiring."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from aegis_core.config.build import build_exporters
from aegis_core.config.models import AegisConfig, ExporterConfig, ProviderConfig, RouteConfig
from aegis_core.errors import AegisConfigValidationError, AegisPluginNotFoundError
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing import FakeProvider
from aegis_core.testing.exporters import ExporterContractKit
from aegis_server.app import create_app
from aegis_server.exporters import JsonlExporter, WebhookExporter
from aegis_server.store.exporting import ExportingLedgerStore
from aegis_server.store.ledger import InMemoryLedgerStore
from aegis_server.telemetry import aegis_exporter_failures_total


class _Collect:
    def __init__(self, name: str = "collect") -> None:
        self.name = name
        self.records: list[dict] = []

    async def export(self, records: list[dict]) -> None:
        await asyncio.sleep(0)  # yield, so ordering is actually exercised
        self.records.extend(records)


class _Broken:
    name = "broken"

    async def export(self, records: list[dict]) -> None:
        raise RuntimeError("destination down")


# ── Built-in exporters ────────────────────────────────────────────────────────


async def test_jsonl_exporter_appends_one_line_per_record(tmp_path: Path) -> None:
    path = tmp_path / "out" / "evidence.jsonl"
    exporter = JsonlExporter(path)
    await ExporterContractKit(exporter).assert_all_async()
    await exporter.export([{"seq": 2, "hash": "b"}])

    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1]) == {"hash": "b", "seq": 2}


async def test_webhook_exporter_posts_records_with_resolved_secret_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    cfg = ExporterConfig.model_validate(
        {
            "type": "webhook",
            "url": "https://siem.example.com/ingest",
            "headers": {"Authorization": SecretStr("Bearer s3cret")},
        }
    )
    exporter = WebhookExporter.from_config("siem", cfg)
    exporter._transport = httpx.MockTransport(handler)
    await exporter.export([{"seq": 1}])

    assert seen[0].headers["authorization"] == "Bearer s3cret"
    assert json.loads(seen[0].content) == {"records": [{"seq": 1}]}


async def test_webhook_exporter_raises_on_error_status() -> None:
    exporter = WebhookExporter(
        "https://siem.example.com", transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await exporter.export([{"seq": 1}])


def test_builtin_exporters_require_their_options() -> None:
    with pytest.raises(AegisConfigValidationError, match="requires 'path'"):
        JsonlExporter.from_config("archive", ExporterConfig(type="jsonl"))
    with pytest.raises(AegisConfigValidationError, match="requires 'url'"):
        WebhookExporter.from_config("siem", ExporterConfig(type="webhook"))


# ── Forwarding ledger ─────────────────────────────────────────────────────────


async def test_records_are_forwarded_in_ledger_order() -> None:
    sink = _Collect()
    store = ExportingLedgerStore(InMemoryLedgerStore(), [sink])
    for i in range(5):
        await store.append(None, {"record_type": "test", "i": i})
    await store.drain()

    assert [r["seq"] for r in sink.records] == [1, 2, 3, 4, 5]
    assert sink.records == await store.list_records()
    await store.aclose()


async def test_failing_exporter_is_isolated_and_counted() -> None:
    sink = _Collect()
    before = aegis_exporter_failures_total.labels(exporter="broken")._value.get()
    store = ExportingLedgerStore(InMemoryLedgerStore(), [_Broken(), sink])

    record = await store.append(None, {"record_type": "test"})  # must not raise
    await store.drain()

    assert record["seq"] == 1
    assert sink.records == [record]
    assert aegis_exporter_failures_total.labels(exporter="broken")._value.get() == before + 1
    await store.aclose()


def test_runs_reach_exporters_end_to_end() -> None:
    sink = _Collect()
    executor = PipelineExecutor()
    executor.register("default", provider=FakeProvider())
    store = ExportingLedgerStore(InMemoryLedgerStore(), [sink])

    with TestClient(create_app(executor, no_auth=True, ledger_store=store)) as client:
        client.post("/v1/runs", json={"messages": [{"role": "user", "content": "hi"}]})
    # Leaving the client runs shutdown, which flushes the exporter queues.

    types = [r["record_type"] for r in sink.records]
    assert types == ["model_inventory", "run_evidence"]


# ── Config wiring ─────────────────────────────────────────────────────────────


def _cfg(**exporters: dict) -> AegisConfig:
    return AegisConfig(
        providers={"fake": ProviderConfig(type="fake")},
        routes={"default": RouteConfig(provider="fake")},
        exporters={k: ExporterConfig.model_validate(v) for k, v in exporters.items()},
    )


def test_build_exporters_from_config(tmp_path: Path) -> None:
    exporters = build_exporters(_cfg(archive={"type": "jsonl", "path": str(tmp_path / "e.jsonl")}))
    assert [e.name for e in exporters] == ["archive"]
    assert isinstance(exporters[0], JsonlExporter)


def test_build_exporters_unknown_type() -> None:
    registry = MagicMock()
    registry.load.side_effect = AegisPluginNotFoundError()
    registry.list_plugins.return_value = []
    with pytest.raises(AegisConfigValidationError, match="unknown exporter type 'kafka'"):
        build_exporters(_cfg(stream={"type": "kafka"}), registry=registry)


def test_build_exporters_rejects_non_exporters() -> None:
    registry = MagicMock()
    registry.load.return_value = object
    with pytest.raises(AegisConfigValidationError, match="did not produce an Exporter"):
        build_exporters(_cfg(bad={"type": "bad"}), registry=registry)
