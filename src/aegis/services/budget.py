from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass
class TeamBudget:
    team_id: str
    monthly_limit_usd: float
    spent_usd: float = 0.0


class BudgetService:
    """
    Enforces per-team monthly spending caps.
    In production this reads from and writes to TimescaleDB.
    Phase 1 uses an in-memory store; persistence added in Phase 2.
    """

    ALERT_THRESHOLD = 0.70
    HARD_CAP_THRESHOLD = 1.00

    def __init__(self) -> None:
        self._budgets: dict[str, TeamBudget] = {}
        self._lock = threading.Lock()

    def set_budget(self, team_id: str, monthly_limit_usd: float) -> None:
        with self._lock:
            existing = self._budgets.get(team_id)
            spent = existing.spent_usd if existing else 0.0
            self._budgets[team_id] = TeamBudget(team_id, monthly_limit_usd, spent)

    def get_remaining(self, team_id: str) -> float:
        with self._lock:
            b = self._budgets.get(team_id)
            if b is None:
                return float("inf")
            return max(0.0, b.monthly_limit_usd - b.spent_usd)

    def check(self, team_id: str, estimated_cost_usd: float) -> tuple[bool, str]:
        remaining = self.get_remaining(team_id)
        if remaining < estimated_cost_usd:
            return False, f"Budget exceeded: ${estimated_cost_usd:.4f} requested, ${remaining:.4f} remaining"
        return True, "ok"

    def record_spend(self, team_id: str, cost_usd: float) -> None:
        with self._lock:
            b = self._budgets.get(team_id)
            if b:
                b.spent_usd += cost_usd

    def utilization(self, team_id: str) -> Optional[float]:
        with self._lock:
            b = self._budgets.get(team_id)
            if b is None or b.monthly_limit_usd == 0:
                return None
            return b.spent_usd / b.monthly_limit_usd
