"""POST /v1/chat/completions — OpenAI-compatible endpoint (streaming + non-streaming).

PROJECT_SPEC D9 / D12:
- Non-streaming: returns a single JSON completion.
- Streaming (stream=true): returns OpenAI-format Server-Sent Events.
  - TRUE_STREAMING route: runs ingress, then streams provider chunks through
    incremental egress guards.
  - BUFFERED route: runs the full pipeline then replays the result as SSE.
- Every run, on every path, is written to the run store and evidence ledger.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from aegis_core.pipeline.assembler import StreamCapability
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunEvent, RunState
from aegis_core.providers.models import CompletionRequest, Message
from aegis_server.auth.protocol import Principal
from aegis_server.store.run_store import RunRecord
from aegis_server.telemetry import run_span

router = APIRouter()


class _ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[_ChatMessage]
    stream: bool = False


class _Choice(BaseModel):
    index: int
    message: _ChatMessage
    finish_reason: str


class _Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[_Choice]
    usage: _Usage


# ---------------------------------------------------------------------------
# SSE generators
# ---------------------------------------------------------------------------


def _chunk_frame(completion_id: str, model: str, content: str, finish_reason: str | None) -> str:
    return json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    })


def _violation_frame(completion_id: str, model: str, aegis_event: str) -> str:
    return json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "content_filter",
            }
        ],
        "aegis_event": aegis_event,
    })


def _verdict_event(guard: Any, verdict: Any, position: str) -> RunEvent:
    return RunEvent(
        stage="egress",
        node=guard.name,
        event_type="verdict",
        data={
            "verdict": verdict.kind.value,
            "guard": guard.name,
            "reason": verdict.reason,
            "position": position,
        },
    )


async def _record_run(app_state: Any, result: RunState, created_at: str) -> None:
    """Persist a finished (or paused) chat run to the run store and evidence ledger.

    Paused runs must be in the run store for ``POST /v1/runs/{id}/resume`` to
    find them; every run, whatever its outcome, gets a ``run_evidence`` record.
    """
    config_digest = getattr(app_state, "config_digest", None)
    events = [e.to_dict() for e in result.events]
    run_store = getattr(app_state, "run_store", None)
    if run_store is not None:
        await run_store.create(
            RunRecord(
                run_id=result.run_id,
                route=result.route,
                principal_id=result.principal or "",
                status=result.status,
                created_at=created_at,
                events=events,
                config_digest=config_digest,
            )
        )

    ledger_store = getattr(app_state, "ledger_store", None)
    if ledger_store is not None:
        from aegis_server.store.ledger import make_run_evidence

        evidence = SimpleNamespace(
            run_id=result.run_id,
            route=result.route,
            config_digest=config_digest,
            principal_id=result.principal or "",
            created_at=created_at,
            status=result.status,
            events=events,
        )
        completed_at = datetime.now(tz=UTC).isoformat()
        await ledger_store.append(result.run_id, make_run_evidence(evidence, completed_at))


def _held_frame(completion_id: str, model: str, result: RunState) -> str:
    """Terminal frame for a run that was blocked, paused or denied."""
    frame = json.loads(_violation_frame(completion_id, model, result.status))
    frame["aegis_run_id"] = result.run_id
    return json.dumps(frame)


async def _true_stream_gen(
    pipeline: Any,
    state: RunState,
    completion_id: str,
    model: str,
    app_state: Any,
) -> AsyncGenerator[dict[str, str], None]:
    """True-streaming generator.

    1. Run every ingress node (masking, residency, budgets, ...) first.
    2. Stream the provider's output for the *ingress-processed* messages,
       scanning each chunk with the route's incremental egress guards.
    3. Run ``finalize()`` before releasing the ``stop`` frame.
    4. Record the run exactly like the buffered path does.
    """
    created_at = datetime.now(tz=UTC).isoformat()
    violation: str | None = None
    async with run_span(state.route, state.run_id, state.principal or "") as (span, status):
        pre = await pipeline.run_ingress(state)

        if pre.status == "paused":
            # Re-run through the checkpointed graph so the pause is resumable.
            result = await pipeline.run(state)
        elif pre.status in ("blocked", "denied"):
            result = pre
        else:
            result = pre
            req = CompletionRequest(messages=pre.messages, model="", stream=True)
            accumulated = ""
            async for chunk in await pipeline._provider.stream(req):
                for guard in pipeline._incremental_egress_guards:
                    v = await guard.scan_chunk(chunk.text)
                    if v.is_block:
                        result.events.append(_verdict_event(guard, v, "chunk"))
                        violation = "stream_violation"
                        break
                if violation:
                    break
                accumulated += chunk.text
                # Hold back the stop reason until finalize passes.
                yield {
                    "data": _chunk_frame(
                        completion_id,
                        model,
                        chunk.text,
                        finish_reason=None if chunk.finish_reason == "stop" else chunk.finish_reason,
                    )
                }

            if violation is None:
                for guard in pipeline._incremental_egress_guards:
                    v = await guard.finalize(accumulated)
                    result.events.append(_verdict_event(guard, v, "finalize"))
                    if v.is_block:
                        violation = "late_violation"
                        break

            result.response = accumulated
            result.status = "blocked" if violation else "completed"

        status[0] = result.status
        span.set_attribute("run.status", result.status)
        await _record_run(app_state, result, created_at)

    if violation:
        yield {"data": _violation_frame(completion_id, model, violation)}
    elif result.status != "completed":
        yield {"data": _held_frame(completion_id, model, result)}
    else:
        yield {"data": _chunk_frame(completion_id, model, "", finish_reason="stop")}
    yield {"data": "[DONE]"}


async def _buffered_stream_gen(
    pipeline: Any,
    state: RunState,
    completion_id: str,
    model: str,
    app_state: Any,
) -> AsyncGenerator[dict[str, str], None]:
    """Buffered streaming: run the full pipeline, then replay the result as SSE frames."""
    created_at = datetime.now(tz=UTC).isoformat()
    async with run_span(state.route, state.run_id, state.principal or "") as (span, status):
        result = await pipeline.run(state)
        status[0] = result.status
        span.set_attribute("run.status", result.status)
    await _record_run(app_state, result, created_at)

    if result.status != "completed":
        yield {"data": _held_frame(completion_id, model, result)}
    else:
        yield {
            "data": _chunk_frame(completion_id, model, result.response or "", finish_reason="stop")
        }
    yield {"data": "[DONE]"}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/v1/models")
async def list_models(request: Request) -> dict[str, Any]:
    """OpenAI-compatible model list: every Aegis route is exposed as a model id."""
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    return {
        "object": "list",
        "data": [
            {"id": route, "object": "model", "created": 0, "owned_by": "aegis"}
            for route in executor.routes()
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
) -> Response:
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]
    route = body.model
    try:
        pipeline = executor.get(route)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No pipeline for route '{route}'") from exc

    messages = [Message(role=m.role, content=m.content) for m in body.messages]
    state = RunState(
        run_id=str(uuid.uuid4()),
        route=route,
        messages=messages,
        principal=principal.id,
    )

    if body.stream:
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        true_stream = (
            pipeline.stream_capability == StreamCapability.TRUE_STREAMING
            and pipeline._provider is not None
        )
        stream_gen = _true_stream_gen if true_stream else _buffered_stream_gen
        return EventSourceResponse(
            stream_gen(pipeline, state, completion_id, route, request.app.state)
        )

    created_at = datetime.now(tz=UTC).isoformat()
    async with run_span(route, state.run_id, principal.id) as (span, status):
        result = await pipeline.run(state)
        status[0] = result.status
        span.set_attribute("run.status", result.status)
    await _record_run(request.app.state, result, created_at)

    return ChatCompletionResponse(  # type: ignore[return-value]
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        object="chat.completion",
        created=int(time.time()),
        model=body.model,
        choices=[
            _Choice(
                index=0,
                message=_ChatMessage(role="assistant", content=result.response or ""),
                # blocked / paused / denied: the response was withheld
                finish_reason="stop" if result.status == "completed" else "content_filter",
            )
        ],
        usage=_Usage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
