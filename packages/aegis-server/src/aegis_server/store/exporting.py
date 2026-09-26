"""ExportingLedgerStore — forwards every appended ledger record to exporters."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aegis_server.store.ledger import LedgerStore

logger = logging.getLogger("aegis.exporters")


class ExportingLedgerStore:
    """Wraps a :class:`LedgerStore`; each appended record is also sent to exporters.

    The wrapped ledger stays the source of truth: a record is committed there
    first, then queued for every exporter. Each exporter has its own queue and
    worker, so records reach it in ledger order and a slow or failing
    destination never delays a request or affects other exporters. Delivery
    failures are logged and counted in ``aegis_exporter_failures_total``;
    backfill a destination from ``aegis audit export --since-seq N``.
    """

    def __init__(self, inner: LedgerStore, exporters: list[Any]) -> None:
        self._inner = inner
        self._exporters = exporters
        self._queues: dict[str, asyncio.Queue[dict]] = {}
        self._workers: list[asyncio.Task[None]] = []

    @property
    def exporters(self) -> list[Any]:
        return list(self._exporters)

    # ── LedgerStore protocol ───────────────────────────────────────────────

    async def append(self, run_id: str | None, body: dict) -> dict:
        record = await self._inner.append(run_id, body)
        for exporter in self._exporters:
            self._queue_for(exporter).put_nowait(record)
        return record

    async def list_records(self, since_seq: int = 0, route: str | None = None) -> list[dict]:
        return await self._inner.list_records(since_seq=since_seq, route=route)

    async def get_head(self) -> dict | None:
        return await self._inner.get_head()

    # ── Delivery ───────────────────────────────────────────────────────────

    def _queue_for(self, exporter: Any) -> asyncio.Queue[dict]:
        queue = self._queues.get(exporter.name)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[exporter.name] = queue
            self._workers.append(asyncio.create_task(self._deliver(exporter, queue)))
        return queue

    async def _deliver(self, exporter: Any, queue: asyncio.Queue[dict]) -> None:
        from aegis_server.telemetry import aegis_exporter_failures_total

        while True:
            record = await queue.get()
            try:
                await exporter.export([record])
            except Exception:
                aegis_exporter_failures_total.labels(exporter=exporter.name).inc()
                logger.exception(
                    "exporter %r failed to deliver ledger record seq=%s",
                    exporter.name,
                    record.get("seq"),
                )
            finally:
                queue.task_done()

    async def drain(self) -> None:
        """Wait until every queued record has been handed to its exporter."""
        for queue in list(self._queues.values()):
            await queue.join()

    async def aclose(self) -> None:
        """Deliver what is queued, then stop the workers (called on shutdown)."""
        await self.drain()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._queues.clear()
