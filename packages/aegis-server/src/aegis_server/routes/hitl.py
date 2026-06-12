"""HITL (human-in-the-loop) endpoints (PROJECT_SPEC D11/D14).

GET  /v1/runs/{run_id}         — fetch run status
POST /v1/runs/{run_id}/resume  — approve or deny a paused run
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_server.auth.protocol import Principal
from aegis_server.store.run_store import RunStore

router = APIRouter()


class ResumeRequest(BaseModel):
    decision: str  # "approved" | "denied"


class RunStatusResponse(BaseModel):
    run_id: str
    route: str
    principal_id: str
    status: str
    approvers: list[str]


class ResumeResponse(BaseModel):
    run_id: str
    status: str
    response: str | None
    events: list[dict[str, Any]]


@router.get("/v1/runs/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str, request: Request) -> RunStatusResponse:
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    record = await run_store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return RunStatusResponse(
        run_id=record.run_id,
        route=record.route,
        principal_id=record.principal_id,
        status=record.status,
        approvers=record.approvers,
    )


@router.post("/v1/runs/{run_id}/resume", response_model=ResumeResponse)
async def resume_run(run_id: str, body: ResumeRequest, request: Request) -> ResumeResponse:
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]

    record = await run_store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if record.status != "paused":
        raise HTTPException(
            status_code=409, detail=f"Run '{run_id}' is not paused (status: {record.status})."
        )

    # Authorisation: non-empty approvers list restricts who may approve/deny.
    if record.approvers and principal.id not in record.approvers:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AEG-AUTH-003",
                "detail": (
                    f"AEG-AUTH-003: unauthorized approval — principal '{principal.id}'"
                    f" is not an approver for run '{run_id}'."
                ),
            },
        )

    decision: dict[str, object] = {"decision": body.decision}
    try:
        result = await executor.resume(run_id, record.route, decision)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await run_store.update_status(run_id, result.status)
    return ResumeResponse(
        run_id=result.run_id,
        status=result.status,
        response=result.response,
        events=[e.to_dict() for e in result.events],
    )
