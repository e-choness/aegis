"""Tests for guardrail core: Protocol, RegexGuard, GuardNode, and short-circuit pipeline."""

from __future__ import annotations

from aegis_core.guardrails import GuardNode, RegexGuard
from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.assembler import PipelineAssembler
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_core.providers.models import Message
from aegis_core.testing.guardrails import GuardrailContractKit
from aegis_core.testing.providers import FakeProvider


def _make_state(content: str) -> RunState:
    return RunState(
        run_id="test",
        route="default",
        messages=[Message(role="user", content=content)],
    )


# ---------------------------------------------------------------------------
# TestGuardrailProtocol
# ---------------------------------------------------------------------------


class TestGuardrailProtocol:
    def test_regex_guard_is_guardrail(self) -> None:
        guard = RegexGuard(patterns=["foo"], reason="blocked")
        assert isinstance(guard, Guardrail)

    def test_guardrail_has_name(self) -> None:
        guard = RegexGuard(patterns=["foo"], reason="blocked", name="my_guard")
        assert guard.name == "my_guard"

    def test_guardrail_default_name(self) -> None:
        guard = RegexGuard(patterns=["foo"], reason="blocked")
        assert guard.name == "regex"


# ---------------------------------------------------------------------------
# TestRegexGuard
# ---------------------------------------------------------------------------


class TestRegexGuard:
    async def test_blocks_on_match(self) -> None:
        guard = RegexGuard(patterns=["forbidden"], reason="test block")
        verdict = await guard.scan(_make_state("this is forbidden content"))
        assert verdict.is_block
        assert verdict.reason == "test block"

    async def test_allows_no_match(self) -> None:
        guard = RegexGuard(patterns=["forbidden"], reason="blocked")
        verdict = await guard.scan(_make_state("normal content"))
        assert verdict.is_allow

    async def test_case_insensitive(self) -> None:
        guard = RegexGuard(patterns=["FORBIDDEN"], reason="blocked")
        verdict = await guard.scan(_make_state("this is Forbidden content"))
        assert verdict.is_block

    async def test_multiple_patterns_any_matches(self) -> None:
        guard = RegexGuard(patterns=["foo", "bar"], reason="blocked")
        verdict = await guard.scan(_make_state("bar is here"))
        assert verdict.is_block

    async def test_multiple_patterns_none_matches(self) -> None:
        guard = RegexGuard(patterns=["foo", "bar"], reason="blocked")
        verdict = await guard.scan(_make_state("baz is here"))
        assert verdict.is_allow

    async def test_scans_all_messages(self) -> None:
        guard = RegexGuard(patterns=["secret"], reason="blocked")
        state = RunState(
            run_id="test",
            route="default",
            messages=[
                Message(role="user", content="tell me"),
                Message(role="assistant", content="the secret is here"),
            ],
        )
        verdict = await guard.scan(state)
        assert verdict.is_block

    async def test_custom_name(self) -> None:
        guard = RegexGuard(patterns=["x"], reason="blocked", name="my-guard")
        assert guard.name == "my-guard"

    async def test_returns_verdict_allow_type(self) -> None:
        guard = RegexGuard(patterns=["no_match"], reason="blocked")
        verdict = await guard.scan(_make_state("safe"))
        assert isinstance(verdict, Verdict)
        assert verdict.is_allow

    async def test_returns_verdict_block_type(self) -> None:
        guard = RegexGuard(patterns=["bad"], reason="policy")
        verdict = await guard.scan(_make_state("bad word"))
        assert isinstance(verdict, Verdict)
        assert verdict.is_block


# ---------------------------------------------------------------------------
# TestGuardNode
# ---------------------------------------------------------------------------


class _AllowGuard:
    name = "allow_guard"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()


class TestGuardNode:
    async def test_single_allow_no_status_change(self) -> None:
        node = GuardNode([_AllowGuard()])
        delta = await node.run(_make_state("good content"))
        assert delta.status is None
        assert delta.messages is None

    async def test_block_returns_blocked_status(self) -> None:
        guard = RegexGuard(patterns=["bad"], reason="bad content")
        node = GuardNode([guard])
        delta = await node.run(_make_state("bad content"))
        assert delta.status == "blocked"

    async def test_block_short_circuits(self) -> None:
        class _TrackingGuard:
            name = "tracking"
            called = False

            async def scan(self, state: RunState) -> Verdict:
                self.called = True
                return Verdict.allow()

        blocking = RegexGuard(patterns=["bad"], reason="blocked")
        tracker = _TrackingGuard()
        node = GuardNode([blocking, tracker])
        delta = await node.run(_make_state("bad content"))
        assert delta.status == "blocked"
        assert not tracker.called

    async def test_allow_all_produces_events(self) -> None:
        guards: list[Guardrail] = [_AllowGuard(), _AllowGuard()]
        node = GuardNode(guards, name="test_guard")
        delta = await node.run(_make_state("fine"))
        assert delta.events is not None
        assert len(delta.events) == 2
        for evt in delta.events:
            assert evt.event_type == "verdict"
            assert evt.stage == "guard"

    async def test_sanitize_updates_messages(self) -> None:
        class _SanitizeGuard:
            name = "sanitizer"

            async def scan(self, state: RunState) -> Verdict:
                return Verdict.sanitize("[REDACTED]")

        node = GuardNode([_SanitizeGuard()])
        delta = await node.run(_make_state("sensitive data"))
        assert delta.messages is not None
        assert delta.messages[0].content == "[REDACTED]"

    async def test_sanitize_subsequent_guard_sees_sanitized(self) -> None:
        seen: list[str] = []

        class _SanitizeGuard:
            name = "sanitizer"

            async def scan(self, state: RunState) -> Verdict:
                return Verdict.sanitize("[REDACTED]")

        class _InspectGuard:
            name = "inspect"

            async def scan(self, state: RunState) -> Verdict:
                seen.append(state.messages[0].content)
                return Verdict.allow()

        node = GuardNode([_SanitizeGuard(), _InspectGuard()])
        await node.run(_make_state("original content"))
        assert seen == ["[REDACTED]"]

    async def test_require_approval_pauses(self) -> None:
        class _ApprovalGuard:
            name = "approval"

            async def scan(self, state: RunState) -> Verdict:
                return Verdict.require_approval("please review")

        node = GuardNode([_ApprovalGuard()])
        delta = await node.run(_make_state("needs review"))
        assert delta.status == "paused"

    async def test_guard_node_name_default(self) -> None:
        node = GuardNode([])
        assert node.name == "guard"

    async def test_guard_node_custom_name(self) -> None:
        node = GuardNode([], name="ingress")
        assert node.name == "ingress"


# ---------------------------------------------------------------------------
# TestGuardrailContractKit
# ---------------------------------------------------------------------------


class TestGuardrailContractKit:
    def _guard(self) -> RegexGuard:
        return RegexGuard(patterns=["badword"], reason="policy violation", name="kit-guard")

    def test_assert_isinstance(self) -> None:
        GuardrailContractKit(self._guard()).assert_isinstance()

    def test_assert_name(self) -> None:
        GuardrailContractKit(self._guard()).assert_name()

    def test_assert_all_sync(self) -> None:
        GuardrailContractKit(self._guard()).assert_all()

    async def test_assert_scan_returns_verdict(self) -> None:
        await GuardrailContractKit(self._guard()).assert_scan_returns_verdict()

    async def test_assert_blocks(self) -> None:
        await GuardrailContractKit(self._guard()).assert_blocks("badword here")

    async def test_assert_allows(self) -> None:
        await GuardrailContractKit(self._guard()).assert_allows("clean content")

    async def test_assert_all_async(self) -> None:
        await GuardrailContractKit(self._guard()).assert_all_async()


# ---------------------------------------------------------------------------
# TestPipelineShortCircuit
# ---------------------------------------------------------------------------


class TestPipelineShortCircuit:
    async def test_provider_not_called_when_blocked(self) -> None:
        fake = FakeProvider()
        guard = RegexGuard(patterns=["injection"], reason="blocked")
        guard_node = GuardNode([guard], name="ingress_guard")
        pipeline = PipelineAssembler().compile(ingress=[guard_node], provider=fake)

        state = RunState(
            run_id="sc-test",
            route="default",
            messages=[Message(role="user", content="injection attack")],
        )
        result = await pipeline.run(state)

        assert result.status == "blocked"
        assert len(fake.complete_calls) == 0

    async def test_provider_called_when_allowed(self) -> None:
        fake = FakeProvider()
        guard = RegexGuard(patterns=["injection"], reason="blocked")
        guard_node = GuardNode([guard], name="ingress_guard")
        pipeline = PipelineAssembler().compile(ingress=[guard_node], provider=fake)

        state = RunState(
            run_id="sc-test-2",
            route="default",
            messages=[Message(role="user", content="What is 2+2?")],
        )
        result = await pipeline.run(state)

        assert result.status == "completed"
        assert len(fake.complete_calls) == 1

    async def test_two_guards_second_blocked(self) -> None:
        fake = FakeProvider()
        allow_guard = RegexGuard(patterns=["nope"], reason="blocked", name="first")
        block_guard = RegexGuard(patterns=["injection"], reason="blocked", name="second")
        guard_node = GuardNode([allow_guard, block_guard], name="ingress")
        pipeline = PipelineAssembler().compile(ingress=[guard_node], provider=fake)

        state = RunState(
            run_id="sc-test-3",
            route="default",
            messages=[Message(role="user", content="injection attack")],
        )
        result = await pipeline.run(state)

        assert result.status == "blocked"
        assert len(fake.complete_calls) == 0
