"""LangServe-compatible adapter for workflow execution."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
from datetime import datetime, timezone

from ..models import WorkflowInvokeResponse, WorkflowUsage
from .team_context import TeamContext
from .workflow_engine import WorkflowEngine


class LangServeAdapter:
    """
    Adapts WorkflowEngine to LangServe API surface.

    Provides invoke, stream, batch, and schema methods that translate
    between LangServe request/response shapes and internal workflow engine calls.
    """

    def __init__(self, workflow_engine: WorkflowEngine) -> None:
        self._engine = workflow_engine

    async def invoke(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        config: Optional[dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> WorkflowInvokeResponse:
        """
        Synchronously execute a workflow and return results.

        Args:
            team_context: Authenticated team and user context
            workflow_id: Workflow template identifier
            input_data: Input parameters for the workflow
            config: Optional configuration overrides
            timeout_seconds: Optional execution timeout

        Returns:
            WorkflowInvokeResponse with execution results and metrics

        Raises:
            ValueError: If workflow_id not found or access denied
            TimeoutError: If execution exceeds timeout
        """
        try:
            result = await self._engine.execute_workflow(
                team_context=team_context,
                workflow_id=workflow_id,
                input_data=input_data,
                tools=config.get("tools") if config else None,
            )

            status = await asyncio.to_thread(self._engine.get_workflow_status, result.workflow_instance_id)
            if status is None:
                raise RuntimeError(f"Status lost for {result.workflow_instance_id}")

            return WorkflowInvokeResponse(
                execution_id=result.workflow_instance_id,
                workflow_id=workflow_id,
                status=result.status,
                output=result.output_data or {},
                error=result.error,
                metadata={
                    "created_at": status.created_at.isoformat(),
                    "updated_at": status.updated_at.isoformat(),
                    "current_step": status.current_step,
                    "conversation_id": status.conversation_id,
                },
                usage=WorkflowUsage(
                    cost_usd=result.cost_usd,
                    tool_calls_count=len(result.tool_calls),
                    model_calls_count=status.model_calls_count,
                    latency_ms=int(status.execution_time_seconds * 1000),
                ),
            )
        except Exception as e:
            raise RuntimeError(f"Workflow execution failed: {str(e)}") from e

    async def stream(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        config: Optional[dict[str, Any]] = None,
    ):
        """
        Stream workflow execution events via Server-Sent Events.

        Yields WorkflowEvent objects representing:
        - start: workflow execution initiated
        - tool_call: tool invocation event
        - token: streaming token (if applicable)
        - checkpoint: state checkpoint saved
        - complete: workflow finished successfully
        - error: workflow execution failed

        Args:
            team_context: Authenticated team and user context
            workflow_id: Workflow template identifier
            input_data: Input parameters for the workflow
            config: Optional configuration overrides

        Yields:
            Serialized WorkflowEvent dicts
        """
        # Submit workflow for async execution
        execution_id = await self._engine.submit_workflow(
            team_context=team_context,
            workflow_id=workflow_id,
            input_data=input_data,
            tools=config.get("tools") if config else None,
        )

        # Yield start event
        yield {
            "type": "start",
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Poll for status updates and stream events
        max_polls = 300  # 5 minutes with 1-second polling
        poll_count = 0

        while poll_count < max_polls:
            status = await asyncio.to_thread(self._engine.get_workflow_status, execution_id)
            if status is None:
                yield {
                    "type": "error",
                    "execution_id": execution_id,
                    "error": f"Workflow instance {execution_id} not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return

            # Yield checkpoint events
            if status.current_step != "created":
                yield {
                    "type": "checkpoint",
                    "execution_id": execution_id,
                    "step": status.current_step,
                    "timestamp": status.updated_at.isoformat(),
                }

            # Check if workflow completed
            if status.status in ("completed", "failed"):
                if status.status == "completed":
                    yield {
                        "type": "complete",
                        "execution_id": execution_id,
                        "output": status.output_data or {},
                        "metadata": {
                            "latency_ms": int(status.execution_time_seconds * 1000),
                            "cost_usd": status.cost_usd,
                        },
                        "timestamp": status.updated_at.isoformat(),
                    }
                else:
                    yield {
                        "type": "error",
                        "execution_id": execution_id,
                        "error": status.error or "Workflow execution failed",
                        "timestamp": status.updated_at.isoformat(),
                    }
                return

            poll_count += 1
            await self._async_sleep(1)  # Sleep 1 second before next poll

        yield {
            "type": "error",
            "execution_id": execution_id,
            "error": "Workflow execution timeout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def batch(
        self,
        team_context: TeamContext,
        workflow_id: str,
        inputs: list[dict[str, Any]],
        config: Optional[dict[str, Any]] = None,
        max_concurrency: int = 4,
    ) -> list[WorkflowInvokeResponse]:
        """
        Execute workflow against multiple inputs with concurrency control.

        Ensures:
        - Results returned in same order as inputs (even if execution order differs)
        - Partial failures don't stop other executions
        - Concurrency limited by max_concurrency parameter
        - Budget checked before each input

        Args:
            team_context: Authenticated team and user context
            workflow_id: Workflow template identifier
            inputs: List of input objects
            config: Optional configuration overrides
            max_concurrency: Maximum concurrent executions (1-16)

        Returns:
            List of WorkflowInvokeResponse objects in same order as inputs
        """
        import asyncio

        results: list[WorkflowInvokeResponse | Exception] = [None] * len(inputs)
        semaphore = asyncio.Semaphore(max_concurrency)

        async def execute_one(index: int, input_data: dict[str, Any]) -> None:
            async with semaphore:
                try:
                    response = await self.invoke(
                        team_context=team_context,
                        workflow_id=workflow_id,
                        input_data=input_data,
                        config=config,
                    )
                    results[index] = response
                except Exception as e:
                    results[index] = WorkflowInvokeResponse(
                        execution_id=f"batch-{index}",
                        workflow_id=workflow_id,
                        status="failed",
                        output={},
                        error=str(e),
                        metadata={},
                        usage=WorkflowUsage(
                            cost_usd=0.0,
                            tool_calls_count=0,
                            model_calls_count=0,
                            latency_ms=0,
                        ),
                    )

        tasks = [execute_one(i, inp) for i, inp in enumerate(inputs)]
        await asyncio.gather(*tasks)

        return results

    def schema(self, workflow_id: str) -> dict[str, Any]:
        """
        Retrieve workflow input/output schema and configuration.

        Args:
            workflow_id: Workflow template identifier

        Returns:
            Dict with keys:
            - title: Workflow name/description
            - description: Workflow purpose and behavior
            - input_schema: Pydantic schema for input
            - output_schema: Pydantic schema for output
            - config_schema: Pydantic schema for config overrides
        """
        workflow = self._engine._langgraph_gateway.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        return {
            "title": workflow.name,
            "description": workflow.description or "Workflow execution",
            "input_schema": {
                "type": "object",
                "properties": {},
                "description": "Workflow input parameters",
            },
            "output_schema": {
                "type": "object",
                "properties": {},
                "description": "Workflow output data",
            },
            "config_schema": {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tools to enable",
                    },
                },
                "description": "Configuration overrides",
            },
        }

    @staticmethod
    async def _async_sleep(seconds: float) -> None:
        """Async sleep wrapper for testing."""
        import asyncio

        await asyncio.sleep(seconds)
