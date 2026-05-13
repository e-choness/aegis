from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ...services.conversation_storage import ConversationStorage
from ...services.team_context import TeamContext, TeamContextManager

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _team_context(
    request: Request,
    x_team_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TeamContext:
    existing = getattr(request.state, "team_context", None)
    if existing is not None:
        return existing
    if not x_team_id or not x_user_id:
        raise HTTPException(400, "X-Team-ID and X-User-ID headers are required")
    manager: TeamContextManager = getattr(request.app.state, "team_context_manager", None)
    if manager is None:
        raise HTTPException(503, "Team context manager not initialized")
    try:
        return manager.build_context(x_team_id, x_user_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _storage(request: Request) -> ConversationStorage:
    engine = getattr(request.app.state, "workflow_engine", None)
    if engine is None:
        raise HTTPException(503, "Workflow engine not initialized")
    return engine.conversation_storage


@router.get("")
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    workflow_id_filter: Optional[str] = None,
    team_context: TeamContext = Depends(_team_context),
    storage: ConversationStorage = Depends(_storage),
):
    conversations = await storage.list_conversations(
        team_id=team_context.team_id,
        limit=limit,
        offset=offset,
        workflow_id_filter=workflow_id_filter,
    )
    return {"conversations": conversations, "total_count": len(conversations)}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    team_context: TeamContext = Depends(_team_context),
    storage: ConversationStorage = Depends(_storage),
):
    conversation = await storage.get_conversation(conversation_id, team_context.team_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    team_context: TeamContext = Depends(_team_context),
    storage: ConversationStorage = Depends(_storage),
):
    conversation = await storage.get_conversation(conversation_id, team_context.team_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    messages = await storage.get_messages(
        conversation_id,
        limit=limit,
        offset=offset,
        team_id=team_context.team_id,
    )
    return {"messages": [message.to_dict() for message in messages], "total_count": len(messages)}


@router.post("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = "json",
    team_context: TeamContext = Depends(_team_context),
    storage: ConversationStorage = Depends(_storage),
):
    conversation = await storage.get_conversation(conversation_id, team_context.team_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    messages = await storage.get_messages(conversation_id, team_id=team_context.team_id)
    if format == "markdown":
        content = "\n\n".join(f"**{message.role}:** {message.content}" for message in messages)
    elif format == "json":
        content = [message.to_dict() for message in messages]
    else:
        raise HTTPException(400, "format must be markdown or json")
    return {"conversation_id": conversation_id, "format": format, "content": content}


@router.delete("/{conversation_id}", status_code=204)
async def archive_conversation(
    conversation_id: str,
    team_context: TeamContext = Depends(_team_context),
    storage: ConversationStorage = Depends(_storage),
):
    archived = await storage.archive_conversation(conversation_id, team_id=team_context.team_id)
    if not archived:
        raise HTTPException(404, "Conversation not found")
    return None
