"""Tests for Step 05: pipeline runtime — state, verdicts, assembler, executor."""

from __future__ import annotations

import asyncio
import operator
import uuid
from typing import Annotated

import pytest

from aegis_core.pipeline import (
    CompiledPipeline,
    ExecuteNode,
    PipelineAssembler,
    PipelineExecutor,
    PipelineNode,
    RunEvent,
    RunState,
    RunStateDelta,
    Verdict,
    VerdictKind,
)
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(content: str = "hello", route: str = "default") -> RunState:
    return RunState(
        run_id=str(uuid.uuid4()),
        route=route,
        messages=[Message(role="user", content=content)],
    )


class _TrackedNode:
    """Records the order in which it was called."""

    _order_log: list[str]  # shared across instances via assignment in __init__

    def __init__(self, name: str, log: list[str], delta: RunStateDelta | None = None) -> None:
        self.name = name
        self._log = log
        self._delta = delta or RunStateDelta()

    async def run(self, state: RunState) -> RunStateDelta:
        self._log.append(self.name)
        return self._delta


# ---------------------------------------------------------------------------
# RunState + RunStateDelta
# ---------------------------------------------------------------------------

class TestRunState:
    def test_defaults(self) -> None:
        s = RunState(run_id="r1", route="default", messages=[])
        assert s.status == "running"
        assert s.labels == {}
        assert s.mask_map == {}
        assert s.events == []
        assert s.principal is None

    def test_usage_default(self) -> None:
        s = RunState(run_id="r", route="d", messages=[])
        assert s.usage.total_tokens == 0


class TestRunStateDelta:
    def test_all_none_is_noop(self) -> None:
        d = RunStateDelta()
        assert d.labels is None
        assert d.response is None
        assert d.status is None


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_allow(self) -> None:
        v = Verdict.allow()
        assert v.kind == VerdictKind.ALLOW
        assert v.is_allow
        assert not v.is_block

    def test_block(self) -> None:
        v = Verdict.block("contains PII")
        assert v.is_block
        assert v.reason == "contains PII"

    def test_sanitize(self) -> None:
        v = Verdict.sanitize("[MASKED]")
        assert v.is_sanitize
        assert v.replacement == "[MASKED]"

    def test_require_approval(self) -> None:
        v = Verdict.require_approval("Sensitive content detected")
        assert v.is_require_approval
        assert v.prompt == "Sensitive content detected"

    def test_verdict_is_immutable(self) -> None:
        v = Verdict.allow()
        with pytest.raises((AttributeError, TypeError)):
            v.kind = VerdictKind.BLOCK  # type: ignore[misc]

    def test_all_verdict_kinds_covered(self) -> None:
        kinds = {v.value for v in VerdictKind}
        assert kinds == {"allow", "block", "sanitize", "require_approval"}


# ---------------------------------------------------------------------------
# PipelineNode Protocol
# ---------------------------------------------------------------------------

class TestPipelineNodeProtocol:
    def test_execute_node_satisfies_protocol(self) -> None:
        provider = FakeProvider()
        node = ExecuteNode(provider=provider)
        assert isinstance(node, PipelineNode)

    def test_tracked_node_satisfies_protocol(self) -> None:
        log: list[str] = []
        node = _TrackedNode("n", log)
        assert isinstance(node, PipelineNode)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), PipelineNode)


# ---------------------------------------------------------------------------
# Golden path
# ---------------------------------------------------------------------------

class TestGoldenPath:
    def test_request_gets_response(self) -> None:
        provider = FakeProvider(complete_response="hello back")
        pipeline = PipelineAssembler().compile(provider=provider)
        result = asyncio.run(pipeline.run(_make_state("hello")))
        assert result.response == "hello back"

    def test_status_is_completed(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider)
        result = asyncio.run(pipeline.run(_make_state()))
        assert result.status == "completed"

    def test_run_id_preserved(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider)
        state = _make_state()
        result = asyncio.run(pipeline.run(state))
        assert result.run_id == state.run_id

    def test_route_preserved(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider, route="my-route")
        state = _make_state(route="my-route")
        result = asyncio.run(pipeline.run(state))
        assert result.route == "my-route"

    def test_usage_populated(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider)
        result = asyncio.run(pipeline.run(_make_state()))
        assert result.usage.total_tokens > 0


# ---------------------------------------------------------------------------
# Node order
# ---------------------------------------------------------------------------

class TestNodeOrder:
    def test_ingress_before_execute_before_egress(self) -> None:
        log: list[str] = []
        n_in = _TrackedNode("n_in", log)
        n_eg = _TrackedNode("n_eg", log)
        provider = FakeProvider()

        pipeline = PipelineAssembler().compile(
            ingress=[n_in],
            egress=[n_eg],
            provider=provider,
        )
        result = asyncio.run(pipeline.run(_make_state()))

        # verify ordering via node_start events (ExecuteNode doesn't share the log)
        start_nodes = [e.node for e in result.events if e.event_type == "node_start"]
        assert start_nodes.index("n_in") < start_nodes.index("execute")
        assert start_nodes.index("execute") < start_nodes.index("n_eg")

    def test_multiple_ingress_nodes_in_order(self) -> None:
        log: list[str] = []
        n1 = _TrackedNode("n1", log)
        n2 = _TrackedNode("n2", log)
        n3 = _TrackedNode("n3", log)
        provider = FakeProvider()

        pipeline = PipelineAssembler().compile(ingress=[n1, n2, n3], provider=provider)
        asyncio.run(pipeline.run(_make_state()))

        assert log[:3] == ["n1", "n2", "n3"]

    def test_multiple_egress_nodes_in_order(self) -> None:
        log: list[str] = []
        e1 = _TrackedNode("e1", log)
        e2 = _TrackedNode("e2", log)
        provider = FakeProvider()

        pipeline = PipelineAssembler().compile(egress=[e1, e2], provider=provider)
        asyncio.run(pipeline.run(_make_state()))

        assert log == ["e1", "e2"]

    def test_node_names_on_compiled_pipeline(self) -> None:
        log: list[str] = []
        n_in = _TrackedNode("my_in", log)
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(ingress=[n_in], provider=provider)

        assert "my_in" in pipeline.node_names
        assert "execute" in pipeline.node_names


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_execute_node_appends_events(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider)
        result = asyncio.run(pipeline.run(_make_state()))

        node_names_in_events = {e.node for e in result.events}
        assert "execute" in node_names_in_events

    def test_each_node_has_start_and_end_event(self) -> None:
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=provider)
        result = asyncio.run(pipeline.run(_make_state()))

        execute_events = [e for e in result.events if e.node == "execute"]
        types = {e.event_type for e in execute_events}
        assert "node_start" in types
        assert "node_end" in types

    def test_ingress_node_events_appended(self) -> None:
        log: list[str] = []
        n = _TrackedNode("guard1", log)
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(ingress=[n], provider=provider)

        result = asyncio.run(pipeline.run(_make_state()))
        guard_events = [e for e in result.events if e.node == "guard1"]
        assert len(guard_events) >= 2  # at least start + end

    def test_events_are_ordered_chronologically(self) -> None:
        log: list[str] = []
        n_in = _TrackedNode("in1", log)
        n_eg = _TrackedNode("eg1", log)
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(ingress=[n_in], egress=[n_eg], provider=provider)

        result = asyncio.run(pipeline.run(_make_state()))
        nodes_seen = [e.node for e in result.events if e.event_type == "node_start"]
        assert nodes_seen.index("in1") < nodes_seen.index("execute")
        assert nodes_seen.index("execute") < nodes_seen.index("eg1")

    def test_node_delta_events_included(self) -> None:
        extra = RunEvent(stage="ingress", node="custom", event_type="verdict", data={"v": "allow"})
        log: list[str] = []
        n = _TrackedNode("custom", log, delta=RunStateDelta(events=[extra]))
        provider = FakeProvider()
        pipeline = PipelineAssembler().compile(ingress=[n], provider=provider)

        result = asyncio.run(pipeline.run(_make_state()))
        verdict_events = [e for e in result.events if e.event_type == "verdict"]
        assert len(verdict_events) == 1
        assert verdict_events[0].data["v"] == "allow"


# ---------------------------------------------------------------------------
# Custom graph escape hatch (D2)
# ---------------------------------------------------------------------------

class TestCustomGraphEscapeHatch:
    def test_custom_graph_accepted(self) -> None:
        """Pre-compiled LangGraph is accepted without error."""
        from typing import TypedDict

        from langgraph.graph import END, START, StateGraph

        class _S(TypedDict):
            run_id: str
            route: str
            messages: list[dict]
            principal: str | None
            labels: dict
            mask_map: dict
            events: Annotated[list[dict], operator.add]
            prompt_tokens: int
            completion_tokens: int
            total_tokens: int
            cost: float
            response: str | None
            status: str

        async def _noop(state: _S) -> dict:
            return {"response": "custom", "status": "completed", "events": []}

        g = StateGraph(_S)
        g.add_node("noop", _noop)
        g.add_edge(START, "noop")
        g.add_edge("noop", END)
        custom_app = g.compile()

        pipeline = PipelineAssembler().compile(custom_graph=custom_app, route="custom")
        assert isinstance(pipeline, CompiledPipeline)
        assert pipeline.route == "custom"
        assert pipeline.node_names == []

    def test_custom_graph_runs(self) -> None:
        from typing import TypedDict

        from langgraph.graph import END, START, StateGraph

        class _S(TypedDict):
            run_id: str
            route: str
            messages: list[dict]
            principal: str | None
            labels: dict
            mask_map: dict
            events: Annotated[list[dict], operator.add]
            prompt_tokens: int
            completion_tokens: int
            total_tokens: int
            cost: float
            response: str | None
            status: str

        async def _handler(state: _S) -> dict:
            return {"response": "from-custom-graph", "status": "completed", "events": []}

        g = StateGraph(_S)
        g.add_node("handler", _handler)
        g.add_edge(START, "handler")
        g.add_edge("handler", END)

        pipeline = PipelineAssembler().compile(custom_graph=g.compile(), route="custom")
        result = asyncio.run(pipeline.run(_make_state()))
        assert result.response == "from-custom-graph"


# ---------------------------------------------------------------------------
# Graph reuse
# ---------------------------------------------------------------------------

class TestGraphReuse:
    def test_same_compiled_pipeline_reused(self) -> None:
        executor = PipelineExecutor()
        executor.register("default", provider=FakeProvider())

        p1 = executor.get("default")
        p2 = executor.get("default")
        assert p1 is p2

    def test_separate_routes_have_separate_pipelines(self) -> None:
        executor = PipelineExecutor()
        executor.register("route_a", provider=FakeProvider())
        executor.register("route_b", provider=FakeProvider())

        assert executor.get("route_a") is not executor.get("route_b")

    def test_register_returns_compiled_pipeline(self) -> None:
        executor = PipelineExecutor()
        pipeline = executor.register("default", provider=FakeProvider())
        assert isinstance(pipeline, CompiledPipeline)

    def test_get_unknown_route_raises(self) -> None:
        executor = PipelineExecutor()
        with pytest.raises(KeyError, match="ghost"):
            executor.get("ghost")

    def test_executor_run(self) -> None:
        executor = PipelineExecutor()
        executor.register("default", provider=FakeProvider(complete_response="exec result"))
        result = asyncio.run(executor.run("default", _make_state()))
        assert result.response == "exec result"

    def test_routes_list(self) -> None:
        executor = PipelineExecutor()
        executor.register("r1", provider=FakeProvider())
        executor.register("r2", provider=FakeProvider())
        assert set(executor.routes()) == {"r1", "r2"}


# ---------------------------------------------------------------------------
# Assembler validation
# ---------------------------------------------------------------------------

class TestAssemblerValidation:
    def test_no_nodes_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one node"):
            PipelineAssembler().compile()

    def test_compile_with_explicit_execute_node(self) -> None:
        provider = FakeProvider(complete_response="explicit")
        execute = ExecuteNode(provider=provider, name="my_execute")
        pipeline = PipelineAssembler().compile(execute=execute)
        result = asyncio.run(pipeline.run(_make_state()))
        assert result.response == "explicit"
