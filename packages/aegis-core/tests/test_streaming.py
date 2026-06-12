"""Tests for streaming capability negotiation (PROJECT_SPEC D12)."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.guardrails import GuardNode, IncrementalGuardrail, RegexGuard
from aegis_core.guardrails.incremental import IncrementalGuardrail as _IG
from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.assembler import PipelineAssembler, StreamCapability
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_core.testing.providers import FakeProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeIncrementalGuard:
    """Incremental guard that allows all chunks and passes finalize."""

    name = "fake_incremental"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.allow()


class _FakeLateViolationGuard:
    """Incremental guard that always blocks in finalize (late violation)."""

    name = "late_violation"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.block("late violation detected")


# ---------------------------------------------------------------------------
# TestIncrementalGuardrailProtocol
# ---------------------------------------------------------------------------


class TestIncrementalGuardrailProtocol:
    def test_fake_incremental_is_incremental_guardrail(self) -> None:
        assert isinstance(_FakeIncrementalGuard(), IncrementalGuardrail)

    def test_fake_incremental_is_guardrail(self) -> None:
        assert isinstance(_FakeIncrementalGuard(), Guardrail)

    def test_regex_guard_is_not_incremental(self) -> None:
        guard = RegexGuard(patterns=["x"], reason="blocked")
        assert not isinstance(guard, IncrementalGuardrail)

    def test_incremental_has_streaming_literal(self) -> None:
        guard = _FakeIncrementalGuard()
        assert guard.streaming == "incremental"

    def test_regex_guard_streaming_is_none(self) -> None:
        guard = RegexGuard(patterns=["x"], reason="blocked")
        assert guard.streaming == "none"


# ---------------------------------------------------------------------------
# TestGuardNodeStreamCapability
# ---------------------------------------------------------------------------


class TestGuardNodeStreamCapability:
    def test_empty_guards_is_true_streaming(self) -> None:
        node = GuardNode([])
        assert node.stream_capability == "true_streaming"

    def test_all_incremental_is_true_streaming(self) -> None:
        guards: list[Guardrail] = [_FakeIncrementalGuard(), _FakeIncrementalGuard()]
        node = GuardNode(guards, name="egress")
        assert node.stream_capability == "true_streaming"

    def test_one_non_incremental_is_buffered(self) -> None:
        regex = RegexGuard(patterns=["x"], reason="blocked")
        guards: list[Guardrail] = [regex]
        node = GuardNode(guards, name="egress")
        assert node.stream_capability == "buffered"

    def test_mixed_guards_is_buffered(self) -> None:
        guards: list[Guardrail] = [_FakeIncrementalGuard(), RegexGuard(patterns=["x"], reason="r")]
        node = GuardNode(guards, name="egress")
        assert node.stream_capability == "buffered"

    def test_guards_property_returns_copy(self) -> None:
        guard = _FakeIncrementalGuard()
        node = GuardNode([guard])
        returned = node.guards
        assert len(returned) == 1
        returned.clear()
        assert len(node.guards) == 1  # original unaffected


# ---------------------------------------------------------------------------
# TestStreamCapabilityNegotiation
# ---------------------------------------------------------------------------


class TestStreamCapabilityNegotiation:
    def test_no_egress_is_true_streaming(self) -> None:
        fake = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=fake)
        assert pipeline.stream_capability == StreamCapability.TRUE_STREAMING

    def test_incremental_egress_is_true_streaming(self) -> None:
        fake = FakeProvider()
        guards: list[Guardrail] = [_FakeIncrementalGuard()]
        egress_node = GuardNode(guards, name="egress")
        pipeline = PipelineAssembler().compile(
            egress=[egress_node],
            provider=fake,
        )
        assert pipeline.stream_capability == StreamCapability.TRUE_STREAMING

    def test_non_incremental_egress_is_buffered(self) -> None:
        fake = FakeProvider()
        regex = RegexGuard(patterns=["x"], reason="blocked")
        guards: list[Guardrail] = [regex]
        egress_node = GuardNode(guards, name="egress")
        pipeline = PipelineAssembler().compile(
            egress=[egress_node],
            provider=fake,
        )
        assert pipeline.stream_capability == StreamCapability.BUFFERED

    def test_mixed_egress_is_buffered(self) -> None:
        fake = FakeProvider()
        guards: list[Guardrail] = [_FakeIncrementalGuard(), RegexGuard(patterns=["x"], reason="r")]
        egress_node = GuardNode(guards, name="egress")
        pipeline = PipelineAssembler().compile(
            egress=[egress_node],
            provider=fake,
        )
        assert pipeline.stream_capability == StreamCapability.BUFFERED

    def test_true_streaming_pipeline_stores_incremental_guards(self) -> None:
        fake = FakeProvider()
        inc = _FakeIncrementalGuard()
        guards: list[Guardrail] = [inc]
        egress_node = GuardNode(guards, name="egress")
        pipeline = PipelineAssembler().compile(
            egress=[egress_node],
            provider=fake,
        )
        assert len(pipeline._incremental_egress_guards) == 1
        assert isinstance(pipeline._incremental_egress_guards[0], _IG)

    def test_buffered_pipeline_stores_no_incremental_guards(self) -> None:
        fake = FakeProvider()
        regex = RegexGuard(patterns=["x"], reason="blocked")
        guards: list[Guardrail] = [regex]
        egress_node = GuardNode(guards, name="egress")
        pipeline = PipelineAssembler().compile(
            egress=[egress_node],
            provider=fake,
        )
        assert pipeline._incremental_egress_guards == []

    def test_provider_stored_on_pipeline(self) -> None:
        fake = FakeProvider()
        pipeline = PipelineAssembler().compile(provider=fake)
        assert pipeline._provider is fake


# ---------------------------------------------------------------------------
# TestIncrementalGuardMethods
# ---------------------------------------------------------------------------


class TestIncrementalGuardMethods:
    async def test_scan_chunk_allow(self) -> None:
        guard = _FakeIncrementalGuard()
        verdict = await guard.scan_chunk("safe text")
        assert verdict.is_allow

    async def test_finalize_allow(self) -> None:
        guard = _FakeIncrementalGuard()
        verdict = await guard.finalize("safe accumulated text")
        assert verdict.is_allow

    async def test_late_violation_finalize_blocks(self) -> None:
        guard = _FakeLateViolationGuard()
        verdict = await guard.finalize("anything")
        assert verdict.is_block
