"""Pack factory for aegis.budgets — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.config.models import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return the budget check (ingress) and spend recorder (egress).

    Both share one :class:`BudgetLedger`: list the guardrail in ``ingress`` to
    block principals over their cap, and in ``egress`` to charge each run.
    """
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_budgets import BudgetGuard, BudgetLedger, BudgetRecordNode

    default_cap: float = getattr(cfg, "default_cap", 100.0)
    ledger = BudgetLedger(default_cap=default_cap)
    guard = BudgetGuard(ledger, name=name)
    return {
        "ingress": [GuardNode([guard], name=name)],
        "egress": [BudgetRecordNode(guard, name=f"{name}.record")],
    }
