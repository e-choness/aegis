"""POST /v1/chat/completions — OpenAI-compatible non-streaming endpoint (PROJECT_SPEC D9)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
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


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(body: ChatCompletionRequest, request: Request) -> ChatCompletionResponse:
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
    result = await pipeline.run(state)
    return ChatCompletionResponse(
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
