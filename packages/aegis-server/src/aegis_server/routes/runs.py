"""POST /v1/runs — synchronous pipeline run (PROJECT_SPEC D9, D17)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_server.auth.protocol import Principal

router = APIRouter()


class RunRequest(BaseModel):
    messages: list[dict[str, str]]
    route: str = "default"


class RunResponse(BaseModel):
    run_id: str
    response: str | None
    principal_id: str
    events: list[dict[str, Any]]
    status: str


@router.post("/v1/runs", response_model=RunResponse)
async def create_run(body: RunRequest, request: Request) -> RunResponse:
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]
    try:
        pipeline = executor.get(body.route)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No pipeline for route '{body.route}'") from exc
    messages = [Message(role=m["role"], content=m["content"]) for m in body.messages]
    state = RunState(
        run_id=str(uuid.uuid4()),
        route=body.route,
        messages=messages,
        principal=principal.id,
    )
    result = await pipeline.run(state)
    return RunResponse(
        run_id=result.run_id,
        response=result.response,
        principal_id=principal.id,
        events=[e.to_dict() for e in result.events],
        status=result.status,
    )
