"""BudgetRecordNode — egress node that charges a finished run to its principal."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_pack_budgets.guard import BudgetGuard


class BudgetRecordNode:
    """Records the run's token usage and cost against the principal's budget.

    :class:`BudgetGuard` only *checks* the ledger before the provider call;
    this node, placed in ``egress``, is what makes spend accumulate.  The pack
    factory wires both to the same :class:`BudgetLedger`.

    It needs the run's final usage, which only exists once the complete
    response has been produced, so it declares ``stream_capability =
    "buffered"``: routes that enforce budgets buffer streamed responses.
    """

    stream_capability: ClassVar[Literal["buffered"]] = "buffered"

    def __init__(self, guard: BudgetGuard, name: str = "budget.record") -> None:
        self.name = name
        self._guard = guard

    async def run(self, state: RunState) -> RunStateDelta:
        if state.principal is None:
            return RunStateDelta()
        self._guard.record(state)
        return RunStateDelta(
            events=[
                RunEvent(
                    stage="egress",
                    node=self.name,
                    event_type="budget_recorded",
                    data={
                        "principal": state.principal,
                        "tokens": state.usage.total_tokens,
                        "cost": state.usage.cost,
                    },
                )
            ]
        )
