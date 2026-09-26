"""ClassificationNode — regex-based content labeler writing labels.classification."""

from __future__ import annotations

import re
from collections.abc import Sequence

from aegis_core.pipeline.state import RunState, RunStateDelta

#: Credential shapes. Each is specific enough to be worth a label on its own;
#: none matches a bare mention ("rotate your password", "an access token").
SECRET_PATTERNS: list[str] = [
    r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----",  # PEM private key
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",  # AWS access key id
    r"\bAIza[0-9A-Za-z_-]{35}\b",  # Google API key
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}\b|\bgithub_pat_\w{22,}",  # GitHub
    r"\bxox[abprs]-[0-9A-Za-z-]{10,}",  # Slack
    r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}",  # Stripe
    r"\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}",  # JWT
    r"(?i)\bbearer\s+[\w~+/.-]{16,}",  # Authorization: Bearer …
    r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@",  # scheme://user:password@host
    # key: value / KEY=value, including env names such as DB_PASSWORD or AUTH_TOKEN.
    # The value must look like a secret — 6+ characters with a digit or symbol —
    # so "password: required", '"token": null' and "${{ secrets.X }}" don't match.
    r"(?i)\b[\w-]*(?:api[_-]?key|secret|token|passw(?:or)?d|pwd|credentials?)[\w-]*"
    r"[\"'*`]*\s*[=:][\s\"'*`]*"
    r"(?!\$\{|null\b|none\b|true\b|false\b)(?=[^\s\"'`,;]*[\d_!@#%^&*+/=-])[^\s\"'`,;]{6,}",
    # "the password is Tr0ub4dor&3" — the value must contain a digit or symbol
    r"(?i)\b(?:password|passcode|passphrase)\s+(?:is|was)\s+(?=\S*[\d\W])\S{6,}",
    # "the login is ops / Hunter2-Prod"
    r"(?i)\b(?:login|credentials?|creds)\s+(?:is|are)\s+\S+\s*/\s*\S+",
]

# Most severe first: a message with an email *and* a password is a secret.
_DEFAULT_PATTERNS: list[tuple[str, str]] = [
    # (label, pattern)
    *(("secret", p) for p in SECRET_PATTERNS),
    ("financial", r"\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b"),  # credit card
    ("pii", r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b"),  # email
    ("pii", r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),  # US phone
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
