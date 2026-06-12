"""BudgetLedger — in-memory per-principal monthly usage ledger."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class _Entry:
    year: int
    month: int
    tokens: int = 0
    cost: float = 0.0


class BudgetLedger:
    """Tracks per-principal token and cost usage by calendar month.

    Thread-safety is not a concern here — the ledger is mutated only from
    async pipeline calls which are naturally serialised within a run.

    Args:
        caps: Mapping of principal → monthly cap in USD.  ``None`` means
            no limit for that principal.  If a principal is not in *caps*
            the default cap applies.
        default_cap: Monthly cost cap in USD applied to principals not
            listed in *caps*.  ``None`` means unlimited by default.
    """

    def __init__(
        self,
        caps: dict[str, float | None] | None = None,
        default_cap: float | None = None,
    ) -> None:
        self._caps: dict[str, float | None] = caps or {}
        self._default_cap = default_cap
        self._usage: dict[str, _Entry] = {}

    def _key(self, principal: str) -> str:
        now = datetime.datetime.now(tz=datetime.UTC)
        return f"{principal}:{now.year}:{now.month}"

    def _entry(self, principal: str) -> _Entry:
        key = self._key(principal)
        if key not in self._usage:
            now = datetime.datetime.now(tz=datetime.UTC)
            self._usage[key] = _Entry(year=now.year, month=now.month)
        return self._usage[key]

    def cap_for(self, principal: str) -> float | None:
        """Return the monthly cost cap for *principal*, or ``None`` if unlimited."""
        return self._caps.get(principal, self._default_cap)

    def current_cost(self, principal: str) -> float:
        """Return the cost accrued this month for *principal*."""
        return self._entry(principal).cost

    def current_tokens(self, principal: str) -> int:
        """Return the token count accrued this month for *principal*."""
        return self._entry(principal).tokens

    def record(self, principal: str, tokens: int, cost: float) -> None:
        """Accumulate *tokens* and *cost* for *principal* in the current month."""
        entry = self._entry(principal)
        entry.tokens += tokens
        entry.cost += cost

    def is_exceeded(self, principal: str) -> bool:
        """Return ``True`` if *principal* has exceeded their monthly cap."""
        cap = self.cap_for(principal)
        if cap is None:
            return False
        return self.current_cost(principal) >= cap
