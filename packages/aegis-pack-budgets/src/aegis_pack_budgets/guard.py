"""BudgetGuard — pre-flight per-principal monthly budget cap enforcer."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_pack_budgets.ledger import BudgetLedger


class BudgetGuard:
    """A :class:`~aegis_core.guardrails.protocol.Guardrail` that blocks requests
    when a principal has exceeded their monthly cost cap.

    Fail-open for anonymous requests (``state.principal is None``) — no principal
    means no budget to check.  Unlimited principals (``cap is None``) are always
    allowed.

    Args:
        ledger: The :class:`BudgetLedger` holding usage and cap data.
        name: Guard name.
    """

    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(self, ledger: BudgetLedger, name: str = "budget") -> None:
        self.name = name
        self._ledger = ledger

    async def scan(self, state: RunState) -> Verdict:
        """Block if *state.principal* has exceeded their monthly cap."""
        if state.principal is None:
            return Verdict.allow()

        if not self._ledger.is_exceeded(state.principal):
            return Verdict.allow()

        cap = self._ledger.cap_for(state.principal)
        cost = self._ledger.current_cost(state.principal)
        return Verdict.block(
            f"budget: principal '{state.principal}' has exceeded monthly cap "
            f"(spent ${cost:.4f} of ${cap:.4f})"
        )

    def record(self, state: RunState) -> None:
        """Record usage from *state.usage* into the ledger for *state.principal*.

        No-op when ``state.principal is None`` (fail-open — no principal to charge).
        """
        if state.principal is None:
            return
        self._ledger.record(
            state.principal,
            tokens=state.usage.total_tokens,
            cost=state.usage.cost,
        )
