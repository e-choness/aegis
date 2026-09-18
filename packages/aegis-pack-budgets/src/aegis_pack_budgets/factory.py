"""Pack factory for aegis.budgets — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.config.models import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping a BudgetGuard in the ingress stage."""
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_budgets import BudgetGuard, BudgetLedger

    default_cap: float = getattr(cfg, "default_cap", 100.0)
    ledger = BudgetLedger(default_cap=default_cap)
    return {"ingress": [GuardNode([BudgetGuard(ledger, name=name)], name=name)]}
