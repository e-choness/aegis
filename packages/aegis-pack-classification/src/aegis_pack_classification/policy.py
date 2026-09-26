"""LabelPolicyGuard — turn labels written by earlier nodes into verdicts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict

PolicyVerdict = Literal["block", "require_approval", "allow"]
_VERDICTS: tuple[str, ...] = ("block", "require_approval", "allow")


@dataclass(frozen=True)
class PolicyRule:
    """If ``state.labels[label]`` is one of *values*, return *verdict*.

    *min_confidence* applies when the labelling node also records how sure it
    was, under ``"<label>.confidence"`` (a model-backed labeler does; regex
    classification doesn't, and its labels always pass the check).
    """

    label: str
    values: frozenset[str]
    verdict: PolicyVerdict
    reason: str = ""
    min_confidence: float = 0.0

    def matches(self, labels: Mapping[str, str]) -> bool:
        if labels.get(self.label) not in self.values:
            return False
        raw = labels.get(f"{self.label}.confidence")
        if raw is None or not self.min_confidence:
            return True
        try:
            return float(raw) >= self.min_confidence
        except ValueError:
            return False

    def describe(self, labels: Mapping[str, str]) -> str:
        return self.reason or f"policy: {self.label} is {labels.get(self.label)!r}"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PolicyRule:
        """Parse one ``rules:`` entry from ``aegis.yaml``; ``ValueError`` on a bad one.

        ``{when: {label: classification, in: [secret]}, verdict: block, reason: "…"}``
        """
        when = raw.get("when")
        if not isinstance(when, Mapping) or "label" not in when or "in" not in when:
            raise ValueError("each rule needs 'when: {label: <name>, in: [<values>]}'")
        values = when["in"]
        if isinstance(values, str):
            values = [values]
        verdict = raw.get("verdict")
        if verdict not in _VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(_VERDICTS)}, got {verdict!r}")
        min_conf = float(when.get("min_confidence", 0.0))
        if not 0.0 <= min_conf <= 1.0:
            raise ValueError(f"min_confidence must be between 0 and 1, got {min_conf}")
        return cls(
            label=str(when["label"]),
            values=frozenset(str(v) for v in values),
            verdict=verdict,
            reason=str(raw.get("reason", "")),
            min_confidence=min_conf,
        )


class LabelPolicyGuard:
    """A :class:`~aegis_core.guardrails.protocol.Guardrail` that applies the
    first matching :class:`PolicyRule` to ``state.labels``.

    Labelling and deciding are separate on purpose: classification (or a
    model-backed labeler) only describes the content; this guard is where
    you say what each label means for *this* route. No rule matching means
    the request is allowed.
    """

    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(self, rules: Sequence[PolicyRule], name: str = "policy") -> None:
        self.name = name
        self.rules = list(rules)

    async def scan(self, state: RunState) -> Verdict:
        for rule in self.rules:
            if rule.matches(state.labels):
                reason = rule.describe(state.labels)
                if rule.verdict == "block":
                    return Verdict.block(reason)
                if rule.verdict == "require_approval":
                    return Verdict.require_approval(reason)
                return Verdict.allow()
        return Verdict.allow()
