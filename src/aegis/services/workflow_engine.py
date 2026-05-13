from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..telemetry import (
    workflow_cost_usd_total,
    workflow_execution_count,
    workflow_execution_duration_seconds,
)
from .conversation_storage import ConversationStorage, Message
from .langgraph_gateway import LangGraphGateway, WorkflowResult
from .team_context import TeamContext, TeamContextManager
from .workflow_checkpoint import WorkflowCheckpointStore
from .workflow_queue import WorkflowQueue


@dataclass
class WorkflowStatus:
    workflow_instance_id: str
    team_id: str
    user_id: str
    workflow_id: str
    status: str
    current_step: str
    input_data: dict[str, Any]
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    execution_time_seconds: float = 0.0
    cost_usd: float = 0.0
    model_calls_count: int = 0
    tool_calls_count: int = 0
    conversation_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class WorkflowEngine:
    """Main orchestrator for Phase 2 workflow execution and state."""

    def __init__(
        self,
        langgraph_gateway: LangGraphGateway,
        conversation_storage: Optional[ConversationStorage] = None,
        checkpoint_store: Optional[WorkflowCheckpointStore] = None,
        workflow_queue: Optional[WorkflowQueue] = None,
        team_context_manager: Optional[TeamContextManager] = None,
    ) -> None:
        self._langgraph_gateway = langgraph_gateway
        self._conversation_storage = conversation_storage or ConversationStorage()
        self._checkpoint_store = checkpoint_store or WorkflowCheckpointStore()
        self._workflow_queue = workflow_queue or WorkflowQueue()
        self._team_context_manager = team_context_manager or TeamContextManager()
        self._instances: dict[str, WorkflowStatus] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def conversation_storage(self) -> ConversationStorage:
        return self._conversation_storage

    @property
    def checkpoint_store(self) -> WorkflowCheckpointStore:
        return self._checkpoint_store

    @property
    def workflow_queue(self) -> WorkflowQueue:
        return self._workflow_queue

    async def execute_workflow(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        tools: Optional[list[str]] = None,
    ) -> WorkflowResult:
        workflow_instance_id = self._create_instance(team_context, workflow_id, input_data)
        return await self._execute_existing(workflow_instance_id, team_context, tools)

    async def submit_workflow(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        tools: Optional[list[str]] = None,
    ) -> str:
        workflow_instance_id = self._create_instance(team_context, workflow_id, input_data)
        self._tasks[workflow_instance_id] = asyncio.create_task(
            self._execute_existing(workflow_instance_id, team_context, tools)
        )
        return workflow_instance_id

    async def resume_workflow(self, workflow_instance_id: str, user_input: str) -> WorkflowResult:
        status = self._require_instance(workflow_instance_id)
        if status.status == "cancelled":
            raise ValueError("cancelled workflows cannot be resumed")
        team_context = self._team_context_manager.build_context(status.team_id, status.user_id)
        status.input_data = {**status.input_data, "resume_input": user_input}
        status.status = "running"
        status.current_step = "resumed"
        status.updated_at = datetime.now(timezone.utc)
        if status.conversation_id:
            await self._conversation_storage.add_text_message(status.conversation_id, "user", user_input)
        return await self._execute_existing(workflow_instance_id, team_context, None)

    async def cancel_workflow(self, workflow_instance_id: str) -> None:
        status = self._require_instance(workflow_instance_id)
        task = self._tasks.get(workflow_instance_id)
        if task and not task.done():
            task.cancel()
        status.status = "cancelled"
        status.current_step = "cancelled"
        status.updated_at = datetime.now(timezone.utc)

    def get_workflow_status(self, workflow_instance_id: str) -> Optional[WorkflowStatus]:
        return self._instances.get(workflow_instance_id)

    async def get_conversation_history(
        self,
        workflow_instance_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        status = self._require_instance(workflow_instance_id)
        if not status.conversation_id:
            return []
        return await self._conversation_storage.get_messages(
            status.conversation_id,
            limit=limit,
            offset=offset,
            team_id=status.team_id,
        )

    async def queue_workflow(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        priority: int = 5,
    ) -> str:
        workflow = self._langgraph_gateway.get_workflow(workflow_id)
        return await self._workflow_queue.enqueue_workflow(
            team_id=team_context.team_id,
            user_id=team_context.user_id,
            workflow_id=workflow_id,
            input_data=input_data,
            priority=priority,
            cost_estimate_usd=workflow.cost_estimate_usd,
        )

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _create_instance(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
    ) -> str:
        workflow_instance_id = str(uuid.uuid4())
        self._instances[workflow_instance_id] = WorkflowStatus(
            workflow_instance_id=workflow_instance_id,
            team_id=team_context.team_id,
            user_id=team_context.user_id,
            workflow_id=workflow_id,
            status="running",
            current_step="created",
            input_data=dict(input_data),
        )
        return workflow_instance_id

    async def _execute_existing(
        self,
        workflow_instance_id: str,
        team_context: TeamContext,
        tools: Optional[list[str]],
    ) -> WorkflowResult:
        status = self._require_instance(workflow_instance_id)
        started_at = datetime.now(timezone.utc)
        status.current_step = "conversation"
        status.updated_at = started_at

        conversation_id = status.conversation_id
        if conversation_id is None:
            conversation_id = await self._conversation_storage.create_conversation(
                team_id=team_context.team_id,
                user_id=team_context.user_id,
                workflow_id=status.workflow_id,
                metadata={"workflow_instance_id": workflow_instance_id},
            )
            status.conversation_id = conversation_id
            await self._conversation_storage.add_text_message(conversation_id, "user", status.input_data)

        await self._checkpoint_store.create_checkpoint(
            workflow_instance_id,
            "started",
            {"input_data": status.input_data, "conversation_id": conversation_id},
        )

        status.current_step = "langgraph"
        status.updated_at = datetime.now(timezone.utc)
        result = await self._langgraph_gateway.invoke_workflow(
            team_context=team_context,
            workflow_id=status.workflow_id,
            input_data=status.input_data,
            tools=tools,
            workflow_instance_id=workflow_instance_id,
            conversation_id=conversation_id,
        )

        status.status = result.status
        status.current_step = "completed" if result.status == "completed" else "failed"
        status.output_data = result.output_data
        status.error = result.error
        status.cost_usd = result.cost_usd
        status.tool_calls_count = len(result.tool_calls)
        status.execution_time_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - started_at).total_seconds(),
        )
        status.updated_at = datetime.now(timezone.utc)

        await self._conversation_storage.add_text_message(
            conversation_id,
            "assistant",
            result.output_data or {"error": result.error},
            metadata={
                "tool_calls": result.tool_calls,
                "reasoning_steps": result.reasoning_steps,
                "cost_usd": result.cost_usd,
            },
        )
        await self._conversation_storage.update_conversation_state(
            conversation_id,
            {
                "workflow_instance_id": workflow_instance_id,
                "status": status.status,
                "output_data": status.output_data,
            },
        )
        await self._checkpoint_store.create_checkpoint(
            workflow_instance_id,
            status.current_step,
            {
                "output_data": status.output_data,
                "tool_calls": result.tool_calls,
                "reasoning_steps": result.reasoning_steps,
            },
        )

        workflow_execution_count.labels(
            workflow_id=status.workflow_id,
            team_id=status.team_id,
            status=status.status,
        ).inc()
        workflow_execution_duration_seconds.labels(workflow_id=status.workflow_id).observe(
            status.execution_time_seconds
        )
        if result.cost_usd:
            workflow_cost_usd_total.labels(
                team_id=status.team_id,
                workflow_id=status.workflow_id,
            ).inc(result.cost_usd)
            self._team_context_manager.debit_budget(status.team_id, result.cost_usd)

        return result

    def _require_instance(self, workflow_instance_id: str) -> WorkflowStatus:
        try:
            return self._instances[workflow_instance_id]
        except KeyError as exc:
            raise KeyError(f"Workflow instance {workflow_instance_id!r} not found") from exc
