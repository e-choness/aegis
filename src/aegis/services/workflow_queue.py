from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class QueueItem:
    queue_id: str
    team_id: str
    user_id: str
    workflow_id: str
    input_data: dict[str, Any]
    priority: int = 5
    status: str = "pending"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    cost_estimate_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["processed_at"] = self.processed_at.isoformat() if self.processed_at else None
        return data


class WorkflowQueue:
    """Priority queue foundation for RESTRICTED agentic workflows."""

    def __init__(self) -> None:
        self._items: dict[str, QueueItem] = {}

    async def enqueue_workflow(
        self,
        team_id: str,
        user_id: str,
        workflow_id: str,
        input_data: dict[str, Any],
        priority: int = 5,
        cost_estimate_usd: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        queue_id = str(uuid.uuid4())
        self._items[queue_id] = QueueItem(
            queue_id=queue_id,
            team_id=team_id,
            user_id=user_id,
            workflow_id=workflow_id,
            input_data=dict(input_data),
            priority=max(1, min(priority, 10)),
            cost_estimate_usd=cost_estimate_usd,
            metadata=metadata or {},
        )
        return queue_id

    async def get_queue_status(self, queue_id: str, team_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        item = self._items.get(queue_id)
        if item is None or (team_id is not None and item.team_id != team_id):
            return None
        return item.to_dict()

    async def list_queue(
        self,
        team_id: str,
        status_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        items = [item for item in self._items.values() if item.team_id == team_id]
        if status_filter:
            items = [item for item in items if item.status == status_filter]
        items.sort(key=lambda item: (-item.priority, item.created_at))
        return [item.to_dict() for item in items]

    async def update_queue_priority(self, queue_id: str, new_priority: int) -> None:
        item = self._items[queue_id]
        item.priority = max(1, min(new_priority, 10))

    async def mark_completed(self, queue_id: str, result: dict[str, Any]) -> None:
        item = self._items[queue_id]
        item.status = "completed"
        item.result = dict(result)
        item.processed_at = datetime.now(timezone.utc)

    async def mark_failed(self, queue_id: str, error: str) -> None:
        item = self._items[queue_id]
        item.status = "failed"
        item.error = error
        item.processed_at = datetime.now(timezone.utc)

    async def cancel_queue_item(self, queue_id: str, team_id: Optional[str] = None) -> bool:
        item = self._items.get(queue_id)
        if item is None or (team_id is not None and item.team_id != team_id):
            return False
        if item.status in {"completed", "failed"}:
            return False
        item.status = "cancelled"
        item.processed_at = datetime.now(timezone.utc)
        return True
