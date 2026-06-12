"""POST /v1/chat/completions — OpenAI-compatible endpoint (streaming + non-streaming).

PROJECT_SPEC D9 / D12:
- Non-streaming: returns a single JSON completion.
- Streaming (stream=true): returns OpenAI-format Server-Sent Events.
  - TRUE_STREAMING route: streams provider chunks through incremental egress guards.
  - BUFFERED route: runs the full pipeline then replays the result as SSE.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from aegis_core.pipeline.assembler import StreamCapability
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import CompletionRequest, Message
from aegis_server.auth.protocol import Principal

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


async def _true_stream_gen(
    pipeline: Any,
    state: RunState,
    completion_id: str,
    model: str,
) -> AsyncGenerator[dict[str, str], None]:
    """True-streaming generator: forward provider chunks with incremental egress scanning."""
    assert pipeline._provider is not None, "TRUE_STREAMING pipeline must have a provider"

    req = CompletionRequest(messages=state.messages, model=model, stream=True)
    accumulated = ""

    async for chunk in await pipeline._provider.stream(req):
        # Incremental egress scan for each chunk
        for guard in pipeline._incremental_egress_guards:
            v = await guard.scan_chunk(chunk.text)
            if v.is_block:
                yield {"data": _violation_frame(completion_id, model, "stream_violation")}
                yield {"data": "[DONE]"}
                return

        accumulated += chunk.text

        # Emit intermediate chunks with no finish_reason;
        # hold back the stop reason until finalize passes.
        yield {
            "data": _chunk_frame(
                completion_id,
                model,
                chunk.text,
                finish_reason=None if chunk.finish_reason == "stop" else chunk.finish_reason,
            )
        }

    # Finalize pass (hold-back: late violation check before emitting stop).
    for guard in pipeline._incremental_egress_guards:
        v = await guard.finalize(accumulated)
        if v.is_block:
            yield {"data": _violation_frame(completion_id, model, "late_violation")}
            yield {"data": "[DONE]"}
            return

    # Emit final stop frame + done.
    yield {"data": _chunk_frame(completion_id, model, "", finish_reason="stop")}
    yield {"data": "[DONE]"}


async def _buffered_stream_gen(
    pipeline: Any,
    state: RunState,
    completion_id: str,
    model: str,
) -> AsyncGenerator[dict[str, str], None]:
    """Buffered streaming: run full pipeline, then replay result as SSE frames."""
    result = await pipeline.run(state)
    content = result.response or ""

    yield {
        "data": _chunk_frame(completion_id, model, content, finish_reason="stop")
    }
    yield {"data": "[DONE]"}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


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
        if pipeline.stream_capability == StreamCapability.TRUE_STREAMING:
            gen = _true_stream_gen(pipeline, state, completion_id, route)
        else:
            gen = _buffered_stream_gen(pipeline, state, completion_id, route)
        return EventSourceResponse(gen)

    result = await pipeline.run(state)
    return ChatCompletionResponse(  # type: ignore[return-value]
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        object="chat.completion",
        created=int(time.time()),
        model=body.model,
        choices=[
            _Choice(
                index=0,
                message=_ChatMessage(role="assistant", content=result.response or ""),
                finish_reason="stop",
            )
        ],
        usage=_Usage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
