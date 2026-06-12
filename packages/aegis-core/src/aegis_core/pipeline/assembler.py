"""PipelineAssembler — compiles a LangGraph StateGraph from ordered PipelineNode lists.

This is the only module in aegis-core that imports langgraph directly.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aegis_core.pipeline.nodes import ExecuteNode
from aegis_core.pipeline.protocol import PipelineNode
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.providers.models import Message, UsageInfo
from aegis_core.providers.protocol import ModelProvider

# ---------------------------------------------------------------------------
# Streaming capability
# ---------------------------------------------------------------------------

class StreamCapability(StrEnum):
    """Compile-time streaming capability for a route (PROJECT_SPEC D12).

    ``TRUE_STREAMING`` — all egress guards are incremental; the server can
    forward chunks to the client as they arrive.

    ``BUFFERED`` — at least one egress guard is non-incremental; the server
    must complete the full response before egress scanning, then replay it as
    OpenAI SSE frames.
    """

    TRUE_STREAMING = "true_streaming"
    BUFFERED = "buffered"


def _compute_stream_capability(egress_nodes: list[PipelineNode]) -> StreamCapability:
    """Return TRUE_STREAMING only when every egress node reports incremental capability."""
    for node in egress_nodes:
        cap = getattr(node, "stream_capability", "true_streaming")
        if cap == "buffered":
            return StreamCapability.BUFFERED
    return StreamCapability.TRUE_STREAMING


def _collect_incremental_guards(egress_nodes: list[PipelineNode]) -> list[Any]:
    """Flatten all IncrementalGuardrail instances out of egress GuardNodes."""
    from aegis_core.guardrails.incremental import IncrementalGuardrail

    guards: list[Any] = []
    for node in egress_nodes:
        node_guards = getattr(node, "guards", None)
        if node_guards is not None:
            guards.extend(g for g in node_guards if isinstance(g, IncrementalGuardrail))
    return guards

# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class _PipelineStateDict(TypedDict):
    run_id: str
    route: str
    messages: list[dict[str, str]]
    principal: str | None
    labels: dict[str, str]
    mask_map: dict[str, str]
    events: Annotated[list[dict[str, Any]], operator.add]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    response: str | None
    status: str


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _state_to_run_state(s: _PipelineStateDict) -> RunState:
    return RunState(
        run_id=s["run_id"],
        route=s["route"],
        messages=[Message(role=m["role"], content=m["content"]) for m in s["messages"]],
        principal=s.get("principal"),
        labels=dict(s.get("labels") or {}),
        mask_map=dict(s.get("mask_map") or {}),
        usage=UsageInfo(
            prompt_tokens=s.get("prompt_tokens") or 0,
            completion_tokens=s.get("completion_tokens") or 0,
            total_tokens=s.get("total_tokens") or 0,
            cost=float(s.get("cost") or 0.0),
        ),
        response=s.get("response"),
        status=s.get("status") or "running",
    )


def _delta_to_partial(node_name: str, stage: str, delta: RunStateDelta) -> dict[str, Any]:
    result: dict[str, Any] = {}
    new_events: list[dict[str, Any]] = []

    if delta.labels is not None:
        result["labels"] = delta.labels
    if delta.mask_map is not None:
        result["mask_map"] = delta.mask_map
    if delta.messages is not None:
        result["messages"] = [{"role": m.role, "content": m.content} for m in delta.messages]
    if delta.response is not None:
        result["response"] = delta.response
    if delta.status is not None:
        result["status"] = delta.status
    if delta.usage is not None:
        result["prompt_tokens"] = delta.usage.prompt_tokens
        result["completion_tokens"] = delta.usage.completion_tokens
        result["total_tokens"] = delta.usage.total_tokens
        result["cost"] = delta.usage.cost
    if delta.events:
        new_events.extend(e.to_dict() for e in delta.events)

    result["events"] = new_events
    return result


# ---------------------------------------------------------------------------
# Node wrapper
# ---------------------------------------------------------------------------

def _make_short_circuit_router(next_node: str) -> Callable[[_PipelineStateDict], str]:
    """Return a conditional-edge router that goes to END when blocked or paused."""

    def _router(state: _PipelineStateDict) -> str:
        if state.get("status") in ("blocked", "paused"):
            return END
        return next_node

    return _router


def _wrap_node(node: PipelineNode, stage: str) -> Callable[..., Any]:
    """Wrap a PipelineNode in a LangGraph-compatible async function."""

    async def _fn(state: _PipelineStateDict) -> dict[str, Any]:
        start_evt: dict[str, Any] = {
            "stage": stage,
            "node": node.name,
            "event_type": "node_start",
            "data": {},
        }
        run_state = _state_to_run_state(state)
        delta = await node.run(run_state)
        end_evt: dict[str, Any] = {
            "stage": stage,
            "node": node.name,
            "event_type": "node_end",
            "data": {"status": delta.status} if delta.status else {},
        }
        partial = _delta_to_partial(node.name, stage, delta)
        partial["events"] = [start_evt, *partial.get("events", []), end_evt]
        return partial

    _fn.__name__ = node.name
    return _fn


# ---------------------------------------------------------------------------
# Compiled pipeline
# ---------------------------------------------------------------------------

class CompiledPipeline:
    """A compiled LangGraph app ready to execute.

    Produced by :class:`PipelineAssembler`. Instances are cached per route
    and reused across requests.

    Attributes:
        stream_capability: Compile-time negotiated streaming mode
            (:class:`StreamCapability`).  Used by the server to decide
            whether to true-stream or buffer before emitting SSE.
    """

    def __init__(
        self,
        app: Any,
        route: str,
        node_names: list[str],
        stream_capability: StreamCapability = StreamCapability.BUFFERED,
        provider: ModelProvider | None = None,
        incremental_egress_guards: list[Any] | None = None,
    ) -> None:
        self._app = app
        self.route = route
        self.node_names = node_names
        self.stream_capability = stream_capability
        self._provider = provider
        self._incremental_egress_guards: list[Any] = incremental_egress_guards or []

    async def run(self, state: RunState) -> RunState:
        """Execute the compiled graph and return the final RunState."""
        initial: _PipelineStateDict = {
            "run_id": state.run_id,
            "route": state.route,
            "messages": [{"role": m.role, "content": m.content} for m in state.messages],
            "principal": state.principal,
            "labels": state.labels,
            "mask_map": state.mask_map,
            "events": [],
            "prompt_tokens": state.usage.prompt_tokens,
            "completion_tokens": state.usage.completion_tokens,
            "total_tokens": state.usage.total_tokens,
            "cost": state.usage.cost,
            "response": state.response,
            "status": state.status,
        }
        final = await self._app.ainvoke(initial)
        return RunState(
            run_id=final["run_id"],
            route=final["route"],
            messages=[Message(role=m["role"], content=m["content"]) for m in final["messages"]],
            principal=final.get("principal"),
            labels=final.get("labels") or {},
            mask_map=final.get("mask_map") or {},
            events=[
                RunEvent(
                    stage=e["stage"],
                    node=e["node"],
                    event_type=e["event_type"],
                    data=e.get("data") or {},
                )
                for e in final.get("events") or []
            ],
            usage=UsageInfo(
                prompt_tokens=final.get("prompt_tokens") or 0,
                completion_tokens=final.get("completion_tokens") or 0,
                total_tokens=final.get("total_tokens") or 0,
                cost=float(final.get("cost") or 0.0),
            ),
            response=final.get("response"),
            status=final.get("status") or "completed",
        )


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

class PipelineAssembler:
    """Compiles a LangGraph StateGraph from ordered PipelineNode lists.

    Staged spine: ingress → execute → egress (PROJECT_SPEC §2b / D2).
    """

    def compile(
        self,
        ingress: list[PipelineNode] | None = None,
        execute: PipelineNode | None = None,
        egress: list[PipelineNode] | None = None,
        route: str = "default",
        provider: ModelProvider | None = None,
        custom_graph: Any | None = None,
    ) -> CompiledPipeline:
        """Compile and return a :class:`CompiledPipeline`.

        Args:
            ingress: Nodes to run before the execute stage, in order.
            execute: Explicit execute node. If *None* and *provider* is given,
                an :class:`ExecuteNode` is created automatically.
            egress: Nodes to run after the execute stage, in order.
            route: Route identifier (stored on the compiled pipeline).
            provider: ModelProvider used when *execute* is not given.
            custom_graph: Pre-compiled LangGraph app (escape hatch, D2).
                When supplied, all other arguments except *route* are ignored.

        Returns:
            A :class:`CompiledPipeline` wrapping the compiled graph.
        """
        if custom_graph is not None:
            return CompiledPipeline(
                custom_graph,
                route=route,
                node_names=[],
                stream_capability=StreamCapability.BUFFERED,
            )

        ingress_nodes = ingress or []
        egress_nodes = egress or []

        if execute is None and provider is not None:
            execute = ExecuteNode(provider=provider)

        # Build ordered list: (node, stage_name)
        ordered: list[tuple[PipelineNode, str]] = []
        for n in ingress_nodes:
            ordered.append((n, "ingress"))
        if execute is not None:
            ordered.append((execute, "execute"))
        for n in egress_nodes:
            ordered.append((n, "egress"))

        if not ordered:
            raise ValueError(
                "PipelineAssembler.compile() requires at least one node. "
                "Supply a *provider*, an explicit *execute* node, or *ingress*/*egress* nodes."
            )

        graph: StateGraph = StateGraph(_PipelineStateDict)
        node_names: list[str] = []

        for node, stage in ordered:
            graph.add_node(node.name, _wrap_node(node, stage))
            node_names.append(node.name)

        # Chain: START → node_0 → (conditional) → node_1 → … → END
        # After each non-final node, short-circuit to END if blocked or paused.
        graph.add_edge(START, node_names[0])
        for i in range(len(node_names) - 1):
            graph.add_conditional_edges(
                node_names[i],
                _make_short_circuit_router(node_names[i + 1]),
            )
        graph.add_edge(node_names[-1], END)

        stream_cap = _compute_stream_capability(egress_nodes)
        inc_guards = (
            _collect_incremental_guards(egress_nodes)
            if stream_cap == StreamCapability.TRUE_STREAMING
            else []
        )

        return CompiledPipeline(
            graph.compile(),
            route=route,
            node_names=node_names,
            stream_capability=stream_cap,
            provider=provider,
            incremental_egress_guards=inc_guards,
        )
