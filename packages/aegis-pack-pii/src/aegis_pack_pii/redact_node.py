"""PiiRedactNode — removes personal data the model produced itself from its reply."""

from __future__ import annotations

import re
from typing import Any

from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_pack_pii.detection import DEFAULT_ENTITIES, PiiDetector

#: Placeholders the ingress mask put in — the user's own values, restored later.
_PLACEHOLDER = re.compile(r"<[A-Z0-9_]+_\d+>")

#: What the model may not invent in a reply: every default entity but names.
#: The model mentions names constantly (authors, public figures, "Jane" in an
#: example) and name detection is the least precise, so PERSON is opt-in.
DEFAULT_REDACT_ENTITIES: tuple[str, ...] = tuple(e for e in DEFAULT_ENTITIES if e != "PERSON")


class PiiRedactNode:
    """Egress node: redact PII in the model's reply *before* it is unmasked.

    At that point the values the user sent are still placeholders, so any PII
    found was produced by the model — a customer's phone number from its
    training data, an address from a retrieved document. Each is replaced
    with an irreversible ``[ENTITY_TYPE]`` label and the change is recorded
    as a ``sanitize`` verdict (types and counts, never the values).

    Place it before the unmask node — the ``aegis.pii`` pack's egress order
    is ``[<name>.redact, <name>.unmask]``.
    """

    name: str = "pii_redact_node"

    def __init__(self, name: str | None = None, detector: PiiDetector | None = None) -> None:
        if name is not None:
            self.name = name
        self._detector = detector or PiiDetector(entities=DEFAULT_REDACT_ENTITIES)

    def warmup(self) -> None:
        self._detector.warmup()

    async def run(self, state: RunState) -> RunStateDelta:
        text = state.response
        if not text:
            return RunStateDelta()
        taken = [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
        found: list[Any] = sorted(
            (
                r
                for r in self._detector.find(text)
                if not any(r.start < b and a < r.end for a, b in taken)
            ),
            key=lambda r: r.start,
        )
        if not found:
            return RunStateDelta()
        counts: dict[str, int] = {}
        for r in reversed(found):
            text = f"{text[: r.start]}[{r.entity_type}]{text[r.end :]}"
            counts[r.entity_type] = counts.get(r.entity_type, 0) + 1
        summary = ", ".join(f"{n} {etype}" for etype, n in sorted(counts.items()))
        event = RunEvent(
            stage="egress",
            node=self.name,
            event_type="verdict",
            data={
                "verdict": "sanitize",
                "guard": self.name,
                "reason": f"redacted {summary} the model produced itself",
            },
        )
        return RunStateDelta(response=text, events=[event])
