"""POST /v1/runs — synchronous and background pipeline runs (PROJECT_SPEC D9, D14, D17)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_server.auth.protocol import Principal
from aegis_server.recording import record_run
from aegis_server.store.ledger import LedgerStore
from aegis_server.store.run_store import RunRecord, RunStore
from aegis_server.telemetry import run_span

router = APIRouter()

# Module-level set to keep background task references alive until they complete.
_background_tasks: set[asyncio.Task[None]] = set()


class RunRequest(BaseModel):
    messages: list[dict[str, str]]
    route: str = "default"
    approvers: list[str] = []
    background: bool = False


class RunResponse(BaseModel):
    run_id: str
    response: str | None
    principal_id: str
    events: list[dict[str, Any]]
    status: str


@router.post("/v1/runs", response_model=RunResponse)
async def create_run(body: RunRequest, request: Request) -> RunResponse:
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]
    try:
        pipeline = executor.get(body.route)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"No pipeline for route '{body.route}'"
        ) from exc
    messages = [Message(role=m["role"], content=m["content"]) for m in body.messages]
    run_id = str(uuid.uuid4())
    state = RunState(
        run_id=run_id,
        route=body.route,
        messages=messages,
        principal=principal.id,
    )

    if body.background:
        record = RunRecord(
            run_id=run_id,
            route=body.route,
            principal_id=principal.id,
            status="pending",
            approvers=body.approvers,
        )
        await run_store.create(record)
        _tracer = getattr(request.app.state, "tracer", None)
        _config_digest = getattr(request.app.state, "config_digest", None)
        _ledger_store = getattr(request.app.state, "ledger_store", None)
        _task = asyncio.create_task(
            _run_background(
                run_id,
                body.route,
                state,
                pipeline,
                run_store,
                _tracer,
                _config_digest,
                ledger_store=_ledger_store,
                principal_id=principal.id,
                created_at=record.created_at,
            )
        )
        _background_tasks.add(_task)
        _task.add_done_callback(_background_tasks.discard)
        return RunResponse(
            run_id=run_id,
            response=None,
            principal_id=principal.id,
            events=[],
            status="pending",
        )

    # Synchronous path
    record = RunRecord(
        run_id=run_id,
        route=body.route,
        principal_id=principal.id,
        status="running",
        approvers=body.approvers,
    )
    await run_store.create(record)

    tracer = getattr(request.app.state, "tracer", None)
    async with run_span(body.route, run_id, principal.id, tracer=tracer) as (span, status_holder):
        result = await pipeline.run(state)
        span.set_attribute("run.status", result.status)
        status_holder[0] = result.status

    events_dicts = [e.to_dict() for e in result.events]
    await record_run(
        run_store=run_store,
        ledger_store=getattr(request.app.state, "ledger_store", None),
        run_id=run_id,
        route=body.route,
        principal_id=principal.id,
        created_at=getattr(record, "created_at", ""),
        config_digest=getattr(request.app.state, "config_digest", None),
        status=result.status,
        events=events_dicts,
    )

    return RunResponse(
        run_id=result.run_id,
        response=result.response,
        principal_id=principal.id,
        events=events_dicts,
        status=result.status,
    )


async def _run_background(
    run_id: str,
    route: str,
    state: RunState,
    pipeline: object,
    run_store: RunStore,
    tracer: object | None,
    config_digest: str | None = None,
    ledger_store: LedgerStore | None = None,
    principal_id: str = "",
    created_at: str = "",
) -> None:
    """Execute pipeline in background and update run_store on completion."""

    _tracer = tracer if tracer is not None else None  # type: ignore[assignment]
    await run_store.update_status(run_id, "running")
    try:
        async with run_span(
            route,
            run_id,
            state.principal or "",
            tracer=_tracer,  # type: ignore[arg-type]
        ) as (span, status_holder):
            result = await pipeline.run(state)  # type: ignore[union-attr]
            span.set_attribute("run.status", result.status)
            status_holder[0] = result.status
        await record_run(
            run_store=run_store,
            ledger_store=ledger_store,
            run_id=run_id,
            route=route,
            principal_id=principal_id,
            created_at=created_at,
            config_digest=config_digest,
            status=result.status,
            events=[e.to_dict() for e in result.events],
        )
    except Exception:
        await run_store.update_status(run_id, "error")
        raise
