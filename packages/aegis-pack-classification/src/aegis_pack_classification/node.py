"""ClassificationNode — regex-based content labeler writing labels.classification."""

from __future__ import annotations

import re
from collections.abc import Sequence

from aegis_core.pipeline.state import RunState, RunStateDelta

_DEFAULT_PATTERNS: list[tuple[str, str]] = [
    # (label, pattern)
    ("pii", r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b"),          # email
    ("pii", r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),          # US phone
    ("financial", r"\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b"),  # credit card
    ("secret", r"(?i)\b(api[_-]?key|password|secret|token)\s*[=:]\s*\S+"),
    ("medical", r"(?i)\b(diagnosis|prescription|patient|hipaa)\b"),
    ("legal", r"(?i)\b(attorney.client|privileged|confidential)\b"),
    ("public", r".*"),  # catch-all fallback
]


class ClassificationNode:
    """Pipeline node that classifies the last user message via regex rules.

    Writes the matched label into ``state.labels["classification"]``.
    If no pattern matches (impossible with the default catch-all, but possible
    with a custom ``patterns`` list), the label is left unchanged.

    Args:
        patterns: Ordered list of ``(label, regex_pattern)`` pairs.  First
            match wins.  Defaults to a built-in set covering PII, financial,
            secrets, medical, legal, and public content.
        name: Node name.
    """

    def __init__(
        self,
        patterns: Sequence[tuple[str, str]] = _DEFAULT_PATTERNS,
        name: str = "classification",
    ) -> None:
        self.name = name
        self._rules: list[tuple[str, re.Pattern[str]]] = [
            (label, re.compile(pattern)) for label, pattern in patterns
        ]

    async def run(self, state: RunState) -> RunStateDelta:
        """Classify the last user message and return a labels delta."""
        text: str | None = None
        for msg in reversed(state.messages):
            if msg.role == "user":
                text = msg.content
                break

        if text is None:
            return RunStateDelta()

        label = self._classify(text)
        if label is None:
            return RunStateDelta()

        return RunStateDelta(labels={"classification": label})

    def _classify(self, text: str) -> str | None:
        for label, pattern in self._rules:
            if pattern.search(text):
                return label
        return None
