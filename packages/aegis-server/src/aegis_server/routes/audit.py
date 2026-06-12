"""GET /v1/audit — query run records with principal/route/time filters (D14)."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from aegis_server.store.run_store import RunRecord, RunStore

router = APIRouter()


class AuditEntry(RunRecord):
    """Run record serialised for the audit response."""


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
