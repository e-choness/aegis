from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class WorkflowCheckpoint:
    checkpoint_id: str
    workflow_instance_id: str
    step_name: str
    step_index: int
    state: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class WorkflowCheckpointStore:
    """Append-only checkpoint store for pause/resume and auditability."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, list[WorkflowCheckpoint]] = {}

    async def create_checkpoint(
        self,
        workflow_instance_id: str,
        step_name: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        checkpoints = self._checkpoints.setdefault(workflow_instance_id, [])
        checkpoint = WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            workflow_instance_id=workflow_instance_id,
            step_name=step_name,
            step_index=len(checkpoints),
            state=dict(state),
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
            size_bytes=len(json.dumps(state, default=str).encode("utf-8")),
        )
        checkpoints.append(checkpoint)
        return checkpoint.checkpoint_id

    async def get_checkpoint(
        self,
        workflow_instance_id: str,
        checkpoint_id: str,
    ) -> WorkflowCheckpoint:
        for checkpoint in self._checkpoints.get(workflow_instance_id, []):
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        raise KeyError(f"Checkpoint {checkpoint_id!r} not found")

    async def list_checkpoints(self, workflow_instance_id: str) -> list[WorkflowCheckpoint]:
        return list(self._checkpoints.get(workflow_instance_id, []))

    async def restore_from_checkpoint(self, workflow_instance_id: str, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = await self.get_checkpoint(workflow_instance_id, checkpoint_id)
        return dict(checkpoint.state)

    async def cleanup_old_checkpoints(self, workflow_instance_id: str, keep_last_n: int = 10) -> None:
        checkpoints = self._checkpoints.get(workflow_instance_id, [])
        if len(checkpoints) > keep_last_n:
            self._checkpoints[workflow_instance_id] = checkpoints[-keep_last_n:]
