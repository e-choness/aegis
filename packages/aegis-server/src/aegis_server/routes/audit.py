"""GET /v1/audit — query run records with principal/route/time filters (D14)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from aegis_server.store.run_store import RunRecord, RunStore

router = APIRouter()


class AuditEntry(RunRecord):
    """Run record serialised for the audit response."""


@router.get("/v1/audit/ledger")
async def audit_ledger(
    request: Request,
    since_seq: int = Query(default=0, description="Return records with seq > since_seq"),
    route: str | None = Query(default=None, description="Filter by model_id/route"),
) -> dict[str, list[dict]]:
    """Return hash-chained evidence records from the ledger."""
    ledger_store = getattr(request.app.state, "ledger_store", None)
    if ledger_store is None:
        return {"records": []}
    records = await ledger_store.list_records(since_seq=since_seq, route=route)
    return {"records": records}


@router.get("/v1/audit/inventory")
async def audit_inventory(
    request: Request,
    route: str | None = Query(default=None, description="Filter by model_id/route"),
) -> dict[str, list[dict]]:
    """Return model_inventory records from the evidence ledger."""
    ledger_store = getattr(request.app.state, "ledger_store", None)
    if ledger_store is None:
        return {"records": []}
    records = await ledger_store.list_records(route=route)
    inventory = [r for r in records if r.get("record_type") == "model_inventory"]
    return {"records": inventory}


@router.get("/v1/audit/report")
async def audit_report(request: Request) -> dict:
    """Return OSFI E-23 compliance summary: inventory, run stats, chain length."""
    ledger_store = getattr(request.app.state, "ledger_store", None)
    if ledger_store is None:
        return {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "inventory": [],
            "run_stats": {},
            "chain_length": 0,
        }
    records = await ledger_store.list_records(since_seq=0)
    inventory = [r for r in records if r.get("record_type") == "model_inventory"]
    run_records = [r for r in records if r.get("record_type") == "run_evidence"]
    stats: dict[str, int] = {}
    for r in run_records:
        s = r.get("status", "unknown")
        stats[s] = stats.get(s, 0) + 1
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "inventory": inventory,
        "run_stats": stats,
        "chain_length": len(records),
    }


@router.get("/v1/audit")
async def audit_runs(
    request: Request,
    principal: str | None = Query(default=None, description="Filter by principal_id"),
    route: str | None = Query(default=None, description="Filter by route"),
    since: str | None = Query(default=None, description="ISO-8601 lower bound on created_at"),
) -> dict[str, list[dict[str, object]]]:
    """Return run records matching the supplied filters.

    All filters are optional and ANDed together.
    ``since`` compares lexicographically against the ISO-8601 ``created_at``
    field — works correctly for UTC timestamps.
    """
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    records = await run_store.list_runs(principal=principal, route=route, since=since)
    return {"runs": [r.to_dict() for r in records]}
