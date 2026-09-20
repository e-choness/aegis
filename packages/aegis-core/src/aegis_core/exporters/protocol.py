"""Exporter Protocol — the public contract for evidence-ledger exporter implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Exporter(Protocol):
    """Contract for a ledger evidence exporter.

    Implementations register themselves under the ``aegis.exporters``
    entry-point group. An exporter receives already-redacted evidence
    records (as produced by ``aegis_server.store.ledger``) and is
    responsible for delivering them to an external system (a file, an
    object store, Postgres, ...). It must not perform any further
    redaction — that responsibility belongs to the ledger itself.
    """

    name: str

    async def export(self, records: list[dict]) -> None:
        """Deliver *records* to the exporter's destination."""
        ...
