from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, TypedDict

from .team_context import TeamContext
from .tool_registry import ToolRegistry


@dataclass
class WorkflowDefinition:
    workflow_id: str
    name: str
    description: str
    tier_requirement: int = 3
    data_classification: str = "INTERNAL"
    max_steps: int = 10
    timeout_seconds: int = 120
    allowed_tools: list[str] = field(default_factory=list)
    requires_approval: bool = False
    requires_human_in_loop: bool = False
    cost_estimate_usd: float = 0.0
    input_schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        return cls(
            workflow_id=str(data.get("workflow_id") or data.get("id")),
            name=str(data.get("name", data.get("id", "Workflow"))),
            description=str(data.get("description", "")),
            tier_requirement=int(data.get("tier_requirement", 3)),
            data_classification=str(data.get("data_classification", "INTERNAL")),
            max_steps=int(data.get("max_steps", 10)),
            timeout_seconds=int(data.get("timeout_seconds", 120)),
            allowed_tools=list(data.get("allowed_tools", [])),
            requires_approval=bool(data.get("requires_approval", False)),
            requires_human_in_loop=bool(data.get("requires_human_in_loop", False)),
            cost_estimate_usd=float(data.get("cost_estimate_usd", 0.0)),
            input_schema=dict(data.get("input_schema", {})),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowResult:
    workflow_instance_id: str
    team_id: str
    user_id: str
    workflow_id: str
    status: str
    output_data: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    reasoning_steps: list[str]
    cost_usd: float
    latency_ms: int
    conversation_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkflowState(TypedDict, total=False):
    input_data: dict[str, Any]
    selected_tools: list[str]
    tool_calls: list[dict[str, Any]]
    reasoning_steps: list[str]
    output_data: dict[str, Any]
    cost_usd: float


class LangGraphGateway:
    """
    Wrapper for LangGraph workflow execution.

    If `langgraph` is present, workflows run through a small StateGraph. If the
    package is unavailable, the same node functions run linearly so development
    and tests stay Docker-native and deterministic.
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._langgraph_available: Optional[bool] = None

    @property
    def langgraph_available(self) -> bool:
        if self._langgraph_available is None:
            try:
                import langgraph  # noqa: F401
            except Exception:
                self._langgraph_available = False
            else:
                self._langgraph_available = True
        return self._langgraph_available

    async def register_workflow(self, workflow_def: WorkflowDefinition) -> None:
        if not workflow_def.workflow_id:
            raise ValueError("workflow_id is required")
        self._workflows[workflow_def.workflow_id] = workflow_def

    def get_registered_workflows(self) -> list[WorkflowDefinition]:
        return sorted(
            [item for item in self._workflows.values() if item.enabled],
            key=lambda item: item.workflow_id,
        )

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition:
        workflow = self._workflows.get(workflow_id)
        if workflow is None or not workflow.enabled:
            raise KeyError(f"Workflow {workflow_id!r} is not registered")
        return workflow

    def get_workflow_tools(self, workflow_id: str) -> list[str]:
        return list(self.get_workflow(workflow_id).allowed_tools)

    async def invoke_workflow(
        self,
        team_context: TeamContext,
        workflow_id: str,
        input_data: dict[str, Any],
        tools: Optional[list[str]] = None,
        workflow_instance_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> WorkflowResult:
        workflow = self.get_workflow(workflow_id)
        if workflow.cost_estimate_usd > team_context.budget_remaining_usd:
            return WorkflowResult(
                workflow_instance_id=workflow_instance_id or str(uuid.uuid4()),
                team_id=team_context.team_id,
                user_id=team_context.user_id,
                workflow_id=workflow.workflow_id,
                status="failed",
                output_data={},
                tool_calls=[],
                reasoning_steps=["budget_check_failed"],
                cost_usd=0.0,
                latency_ms=0,
                conversation_id=conversation_id,
                error="Insufficient team budget for workflow",
            )

        selected_tools = self._select_tools(workflow, tools)
        start = time.monotonic()
        try:
            initial: WorkflowState = {
                "input_data": dict(input_data),
                "selected_tools": selected_tools,
                "tool_calls": [],
                "reasoning_steps": [],
                "cost_usd": workflow.cost_estimate_usd,
            }
            final_state = await asyncio.wait_for(
                self._run_state_graph(team_context, workflow, initial),
                timeout=max(1, workflow.timeout_seconds),
            )
            status = "completed"
            error = None
        except Exception as exc:
            final_state = {
                "input_data": dict(input_data),
                "selected_tools": selected_tools,
                "tool_calls": [],
                "reasoning_steps": ["workflow_failed"],
                "output_data": {},
                "cost_usd": 0.0,
            }
            status = "failed"
            error = str(exc)

        latency_ms = int((time.monotonic() - start) * 1000)
        return WorkflowResult(
            workflow_instance_id=workflow_instance_id or str(uuid.uuid4()),
            team_id=team_context.team_id,
            user_id=team_context.user_id,
            workflow_id=workflow.workflow_id,
            status=status,
            output_data=dict(final_state.get("output_data", {})),
            tool_calls=list(final_state.get("tool_calls", [])),
            reasoning_steps=list(final_state.get("reasoning_steps", [])),
            cost_usd=float(final_state.get("cost_usd", 0.0)),
            latency_ms=latency_ms,
            conversation_id=conversation_id,
            error=error,
        )

    async def _run_state_graph(
        self,
        team_context: TeamContext,
        workflow: WorkflowDefinition,
        initial_state: WorkflowState,
    ) -> WorkflowState:
        if not self.langgraph_available:
            return await self._run_linear(team_context, workflow, initial_state)

        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return await self._run_linear(team_context, workflow, initial_state)

        async def select_tools(state: WorkflowState) -> WorkflowState:
            return {
                **state,
                "selected_tools": list(state.get("selected_tools", []))[: workflow.max_steps],
                "reasoning_steps": [*state.get("reasoning_steps", []), "select_tools"],
            }

        async def execute_tools(state: WorkflowState) -> WorkflowState:
            return await self._execute_tools_node(team_context, workflow, state)

        async def compose_response(state: WorkflowState) -> WorkflowState:
            return self._compose_response_node(workflow, state)

        graph = StateGraph(WorkflowState)
        graph.add_node("select_tools", select_tools)
        graph.add_node("execute_tools", execute_tools)
        graph.add_node("compose_response", compose_response)
        graph.add_edge(START, "select_tools")
        graph.add_edge("select_tools", "execute_tools")
        graph.add_edge("execute_tools", "compose_response")
        graph.add_edge("compose_response", END)
        compiled = await asyncio.to_thread(graph.compile)
        return await compiled.ainvoke(initial_state)

    async def _run_linear(
        self,
        team_context: TeamContext,
        workflow: WorkflowDefinition,
        initial_state: WorkflowState,
    ) -> WorkflowState:
        state: WorkflowState = {
            **initial_state,
            "selected_tools": list(initial_state.get("selected_tools", []))[: workflow.max_steps],
            "reasoning_steps": [*initial_state.get("reasoning_steps", []), "select_tools"],
        }
        state = await self._execute_tools_node(team_context, workflow, state)
        return self._compose_response_node(workflow, state)

    async def _execute_tools_node(
        self,
        team_context: TeamContext,
        workflow: WorkflowDefinition,
        state: WorkflowState,
    ) -> WorkflowState:
        tool_calls = list(state.get("tool_calls", []))
        total_cost = float(state.get("cost_usd", 0.0))
        for tool_name in state.get("selected_tools", []):
            args = self._build_tool_args(tool_name, state.get("input_data", {}), team_context)
            result = await self._tool_registry.execute_tool(team_context, tool_name, args)
            tool_calls.append(
                {
                    "tool": tool_name,
                    "input": args,
                    "output": result.output,
                    "latency_ms": result.latency_ms,
                    "cost_usd": result.cost_usd,
                }
            )
            total_cost += result.cost_usd
        return {
            **state,
            "tool_calls": tool_calls,
            "cost_usd": total_cost,
            "reasoning_steps": [*state.get("reasoning_steps", []), "execute_tools"],
        }

    def _compose_response_node(self, workflow: WorkflowDefinition, state: WorkflowState) -> WorkflowState:
        input_data = state.get("input_data", {})
        query = input_data.get("query") or input_data.get("question") or input_data.get("prompt") or "workflow input"
        output = {
            "response": f"{workflow.name} completed for: {query}",
            "workflow_id": workflow.workflow_id,
            "tool_call_count": len(state.get("tool_calls", [])),
            "tool_calls": state.get("tool_calls", []),
        }
        return {
            **state,
            "output_data": output,
            "reasoning_steps": [*state.get("reasoning_steps", []), "compose_response"],
        }

    def _select_tools(self, workflow: WorkflowDefinition, requested_tools: Optional[list[str]]) -> list[str]:
        requested = requested_tools if requested_tools is not None else workflow.allowed_tools
        invalid = [tool for tool in requested if tool not in workflow.allowed_tools]
        if invalid:
            raise ValueError(f"Workflow {workflow.workflow_id!r} does not allow tools: {invalid}")
        return list(requested)

    def _build_tool_args(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        team_context: TeamContext,
    ) -> dict[str, Any]:
        query = input_data.get("query") or input_data.get("question") or input_data.get("prompt") or ""
        if tool_name == "web_search":
            return {
                "query": str(query),
                "max_results": int(input_data.get("max_results", 3)),
            }
        if tool_name == "code_execute":
            return {
                "language": str(input_data.get("language", "python")),
                "code": str(input_data.get("code", "")),
                "timeout_seconds": int(input_data.get("timeout_seconds", 10)),
            }
        if tool_name == "database_query":
            return {
                "query": str(input_data.get("sql") or input_data.get("query") or "SELECT * FROM team_data"),
            }
        if tool_name == "vector_search":
            return {
                "query": str(query),
                "top_k": int(input_data.get("top_k", 5)),
            }
        return dict(input_data)
