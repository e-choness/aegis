"""Record a finished (or paused) run: its events in the run store, its evidence in the ledger.

Every path that runs a pipeline — ``/v1/runs`` (sync and background), resume,
and the showcase — records through here, so no run escapes the audit trail.
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import Any

from aegis_server.store.ledger import LedgerStore, make_run_evidence
from aegis_server.store.run_store import RunStore


async def record_run(
    *,
    run_store: RunStore,
    ledger_store: LedgerStore | None,
    run_id: str,
    route: str,
    principal_id: str,
    created_at: str,
    config_digest: str | None,
    status: str,
    events: list[dict[str, Any]],
    approver: dict[str, str] | None = None,
) -> None:
    """Store the run's status and events; append a ``run_evidence`` ledger record."""
    await run_store.update_status(run_id, status)
    await run_store.update_events(run_id, events, config_digest)
    if ledger_store is None:
        return
    run = types.SimpleNamespace(
        run_id=run_id,
        route=route,
        principal_id=principal_id,
        config_digest=config_digest,
        created_at=created_at,
        status=status,
        events=events,
    )
    body = make_run_evidence(run, datetime.now(tz=UTC).isoformat(), approver=approver)
    await ledger_store.append(run_id, body)
