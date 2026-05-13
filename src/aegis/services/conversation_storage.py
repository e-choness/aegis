from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class Message:
    message_id: str
    conversation_id: str
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class Conversation:
    conversation_id: str
    team_id: str
    user_id: str
    workflow_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: Optional[datetime] = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "team_id": self.team_id,
            "user_id": self.user_id,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "archived": self.archived_at is not None,
            "metadata": dict(self.metadata),
        }


class ConversationStorage:
    """Team-scoped conversation and state persistence boundary."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}

    async def create_conversation(
        self,
        team_id: str,
        user_id: str,
        workflow_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        conversation_id = str(uuid.uuid4())
        self._conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            team_id=team_id,
            user_id=user_id,
            workflow_id=workflow_id,
            metadata=metadata or {},
        )
        self._messages[conversation_id] = []
        return conversation_id

    async def add_message(self, conversation_id: str, message: Message) -> None:
        conversation = self._require_conversation(conversation_id)
        self._messages.setdefault(conversation_id, []).append(message)
        conversation.updated_at = datetime.now(timezone.utc)

    async def add_text_message(
        self,
        conversation_id: str,
        role: str,
        content: Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Message:
        if not isinstance(content, str):
            content = json.dumps(content, sort_keys=True)
        message = Message(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        await self.add_message(conversation_id, message)
        return message

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
        team_id: Optional[str] = None,
    ) -> list[Message]:
        conversation = self._require_conversation(conversation_id)
        if team_id is not None and conversation.team_id != team_id:
            return []
        messages = self._messages.get(conversation_id, [])
        return messages[offset : offset + limit]

    async def update_conversation_state(self, conversation_id: str, state: dict[str, Any]) -> None:
        conversation = self._require_conversation(conversation_id)
        conversation.state = dict(state)
        conversation.updated_at = datetime.now(timezone.utc)

    async def get_conversation_state(self, conversation_id: str, team_id: Optional[str] = None) -> dict[str, Any]:
        conversation = self._require_conversation(conversation_id)
        if team_id is not None and conversation.team_id != team_id:
            return {}
        return dict(conversation.state)

    async def list_conversations(
        self,
        team_id: str,
        limit: int = 50,
        offset: int = 0,
        workflow_id_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conversations = [
            item for item in self._conversations.values()
            if item.team_id == team_id and item.archived_at is None
        ]
        if workflow_id_filter:
            conversations = [item for item in conversations if item.workflow_id == workflow_id_filter]
        conversations.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_summary() for item in conversations[offset : offset + limit]]

    async def get_conversation(self, conversation_id: str, team_id: str) -> Optional[dict[str, Any]]:
        conversation = self._conversations.get(conversation_id)
        if conversation is None or conversation.team_id != team_id:
            return None
        return {
            **conversation.to_summary(),
            "state": dict(conversation.state),
            "message_count": len(self._messages.get(conversation_id, [])),
        }

    async def archive_conversation(self, conversation_id: str, team_id: Optional[str] = None) -> bool:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            return False
        if team_id is not None and conversation.team_id != team_id:
            return False
        conversation.archived_at = datetime.now(timezone.utc)
        conversation.updated_at = conversation.archived_at
        return True

    def _require_conversation(self, conversation_id: str) -> Conversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise KeyError(f"Conversation {conversation_id!r} not found") from exc
