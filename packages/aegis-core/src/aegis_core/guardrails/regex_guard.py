"""RegexGuard — built-in guardrail that blocks content matching regex patterns."""

from __future__ import annotations

import re

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class RegexGuard:
    """Blocks any message whose combined content matches one or more regex patterns.

    Args:
        patterns: Regular expressions to test against all message content joined by spaces.
            Matching is performed case-insensitively.
        reason: Human-readable reason included in the block :class:`~aegis_core.pipeline.verdict.Verdict`.
        name: Guard identifier used in :class:`~aegis_core.pipeline.state.RunEvent` audit trails.
    """

    def __init__(
        self,
        patterns: list[str],
        reason: str,
        name: str = "regex",
    ) -> None:
        self.name = name
        self._reason = reason
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

    async def scan(self, state: RunState) -> Verdict:
        combined = " ".join(m.content for m in state.messages)
        for pattern in self._patterns:
            if pattern.search(combined):
                return Verdict.block(self._reason)
        return Verdict.allow()
