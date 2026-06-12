"""Verdict — the sealed return type for all guardrail scans (PROJECT_SPEC §4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VerdictKind(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    SANITIZE = "sanitize"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class Verdict:
    """Result of a guardrail scan.

    Construct via the factory classmethods — do not instantiate directly.
    """

    kind: VerdictKind
    reason: str | None = None
    replacement: str | None = None
    prompt: str | None = None

    # ------------------------------------------------------------------
    # Factory methods (PROJECT_SPEC §4)
    # ------------------------------------------------------------------

    @classmethod
    def allow(cls) -> Verdict:
        """Allow the content unchanged."""
        return cls(kind=VerdictKind.ALLOW)

    @classmethod
    def block(cls, reason: str) -> Verdict:
        """Block the content; attach a human-readable *reason*."""
        return cls(kind=VerdictKind.BLOCK, reason=reason)

    @classmethod
    def sanitize(cls, replacement: str) -> Verdict:
        """Replace the content with *replacement*."""
        return cls(kind=VerdictKind.SANITIZE, replacement=replacement)

    @classmethod
    def require_approval(cls, prompt: str) -> Verdict:
        """Pause the run pending human review; *prompt* explains what to review."""
        return cls(kind=VerdictKind.REQUIRE_APPROVAL, prompt=prompt)

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    @property
    def is_allow(self) -> bool:
        return self.kind == VerdictKind.ALLOW

    @property
    def is_block(self) -> bool:
        return self.kind == VerdictKind.BLOCK

    @property
    def is_sanitize(self) -> bool:
        return self.kind == VerdictKind.SANITIZE

    @property
    def is_require_approval(self) -> bool:
        return self.kind == VerdictKind.REQUIRE_APPROVAL
