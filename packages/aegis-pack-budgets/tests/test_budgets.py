"""Tests for aegis-pack-budgets.

Gate: DC uv run pytest packages/aegis-pack-budgets -q
"""

from __future__ import annotations

from aegis_pack_budgets import BudgetGuard, BudgetLedger

from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message, UsageInfo
from aegis_core.testing.guardrails import GuardrailContractKit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(principal: str | None = "alice", cost: float = 0.0, tokens: int = 0) -> RunState:
    state = RunState(
        run_id="test",
        route="default",
        messages=[Message(role="user", content="hello")],
        principal=principal,
    )
    state.usage = UsageInfo(total_tokens=tokens, cost=cost)
    return state


# ---------------------------------------------------------------------------
# BudgetLedger
# ---------------------------------------------------------------------------


class TestBudgetLedger:
    def test_initial_cost_zero(self) -> None:
        ledger = BudgetLedger()
        assert ledger.current_cost("alice") == 0.0

    def test_initial_tokens_zero(self) -> None:
        ledger = BudgetLedger()
        assert ledger.current_tokens("alice") == 0

    def test_record_accumulates(self) -> None:
        ledger = BudgetLedger()
        ledger.record("alice", tokens=100, cost=0.01)
        ledger.record("alice", tokens=200, cost=0.02)
        assert ledger.current_tokens("alice") == 300
        assert abs(ledger.current_cost("alice") - 0.03) < 1e-9

    def test_different_principals_independent(self) -> None:
        ledger = BudgetLedger()
        ledger.record("alice", tokens=100, cost=0.05)
        ledger.record("bob", tokens=50, cost=0.01)
        assert ledger.current_cost("alice") == 0.05
        assert ledger.current_cost("bob") == 0.01

    def test_cap_for_known_principal(self) -> None:
        ledger = BudgetLedger(caps={"alice": 10.0})
        assert ledger.cap_for("alice") == 10.0

    def test_cap_for_unknown_uses_default(self) -> None:
        ledger = BudgetLedger(default_cap=5.0)
        assert ledger.cap_for("unknown") == 5.0

    def test_cap_none_unlimited(self) -> None:
        ledger = BudgetLedger(caps={"alice": None})
        assert ledger.cap_for("alice") is None

    def test_is_exceeded_under_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 10.0})
        ledger.record("alice", tokens=0, cost=5.0)
        assert not ledger.is_exceeded("alice")

    def test_is_exceeded_at_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 10.0})
        ledger.record("alice", tokens=0, cost=10.0)
        assert ledger.is_exceeded("alice")

    def test_is_exceeded_over_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 5.0})
        ledger.record("alice", tokens=0, cost=7.0)
        assert ledger.is_exceeded("alice")

    def test_is_exceeded_no_cap(self) -> None:
        ledger = BudgetLedger()  # no caps, no default
        ledger.record("alice", tokens=0, cost=99999.0)
        assert not ledger.is_exceeded("alice")


# ---------------------------------------------------------------------------
# BudgetGuard — contract
# ---------------------------------------------------------------------------


class TestBudgetGuardContract:
    def _make_guard(self) -> BudgetGuard:
        return BudgetGuard(ledger=BudgetLedger(caps={"alice": 10.0}))

    async def test_contract_kit(self) -> None:
        kit = GuardrailContractKit(self._make_guard())
        await kit.assert_all_async()

    def test_name_default(self) -> None:
        guard = self._make_guard()
        assert guard.name == "budget"

    def test_name_custom(self) -> None:
        guard = BudgetGuard(ledger=BudgetLedger(), name="my_budget")
        assert guard.name == "my_budget"

    def test_streaming_attribute(self) -> None:
        guard = self._make_guard()
        assert guard.streaming == "none"


# ---------------------------------------------------------------------------
# BudgetGuard — pre-flight checks
# ---------------------------------------------------------------------------


class TestBudgetGuardScan:
    async def test_allows_under_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 10.0})
        ledger.record("alice", tokens=100, cost=5.0)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_allow

    async def test_blocks_at_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 10.0})
        ledger.record("alice", tokens=0, cost=10.0)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_block

    async def test_blocks_over_cap(self) -> None:
        ledger = BudgetLedger(caps={"alice": 5.0})
        ledger.record("alice", tokens=0, cost=7.0)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_block

    async def test_block_reason_mentions_principal(self) -> None:
        ledger = BudgetLedger(caps={"alice": 1.0})
        ledger.record("alice", tokens=0, cost=2.0)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_block
        assert verdict.reason is not None
        assert "alice" in verdict.reason

    async def test_allows_no_cap(self) -> None:
        ledger = BudgetLedger()  # no caps
        ledger.record("alice", tokens=0, cost=99999.0)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_allow

    async def test_anonymous_principal_allow_when_none(self) -> None:
        """principal=None is fail-open — no principal means no budget to check."""
        ledger = BudgetLedger(caps={"anonymous": 0.01})
        ledger.record("anonymous", tokens=0, cost=0.05)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state(principal=None))
        assert verdict.is_allow

    async def test_record_updates_ledger(self) -> None:
        ledger = BudgetLedger(caps={"alice": 1.0})
        guard = BudgetGuard(ledger=ledger)
        state = _state("alice", cost=0.5, tokens=100)
        # pre-flight: allow
        verdict = await guard.scan(state)
        assert verdict.is_allow
        # record usage
        guard.record(state)
        assert abs(ledger.current_cost("alice") - 0.5) < 1e-9
        assert ledger.current_tokens("alice") == 100

    async def test_record_then_exceeded(self) -> None:
        ledger = BudgetLedger(caps={"alice": 0.5})
        guard = BudgetGuard(ledger=ledger)
        # First request exactly at cap
        state1 = _state("alice", cost=0.5, tokens=100)
        verdict1 = await guard.scan(state1)
        assert verdict1.is_allow
        guard.record(state1)
        # After recording 0.5 >= cap 0.5, ledger marks alice exceeded
        # Second request is now blocked pre-flight
        state2 = _state("alice", cost=0.2, tokens=50)
        verdict2 = await guard.scan(state2)
        assert verdict2.is_block

    async def test_block_verdict_includes_audit_event_pattern(self) -> None:
        """block verdict from budget guard is inspectable (kind=block)."""
        ledger = BudgetLedger(caps={"alice": 0.0})
        ledger.record("alice", tokens=0, cost=0.01)
        guard = BudgetGuard(ledger=ledger)
        verdict = await guard.scan(_state("alice"))
        assert verdict.is_block
        assert verdict.kind.value == "block"

    async def test_different_principals_independent(self) -> None:
        ledger = BudgetLedger(caps={"alice": 1.0, "bob": 1.0})
        ledger.record("alice", tokens=0, cost=1.5)  # alice over cap
        guard = BudgetGuard(ledger=ledger)
        alice_verdict = await guard.scan(_state("alice"))
        bob_verdict = await guard.scan(_state("bob"))
        assert alice_verdict.is_block
        assert bob_verdict.is_allow
