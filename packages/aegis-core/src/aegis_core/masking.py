"""Masking — replace sensitive spans with placeholders, and restore them.

Shared by every pack that hides values from the model (PII, secrets, custom
entities), so they all use one placeholder scheme and one ``mask_map``: a
value masked by one pack keeps its placeholder when another pack sees it, and
a single unmask on egress restores everything.

Placeholders look like ``<EMAIL_ADDRESS_0>``: the entity type and a number
per type, in reading order. The same value always gets the same placeholder
within a run, so the model can tell two mentions are the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.providers.models import Message

_PLACEHOLDER = re.compile(r"<([A-Z0-9_]+)_(\d+)>")


class Span(Protocol):
    """Anything with a character range and an entity type (a Presidio result, a :class:`Found`)."""

    @property
    def start(self) -> int: ...
    @property
    def end(self) -> int: ...
    @property
    def entity_type(self) -> str: ...


@dataclass(frozen=True)
class Found:
    """A detected span, for detectors that don't have their own result type."""

    start: int
    end: int
    entity_type: str
    score: float = 1.0


class Placeholders:
    """Allocates placeholders for one run, continuing from its existing ``mask_map``."""

    def __init__(self, existing: dict[str, str]) -> None:
        self.by_value: dict[tuple[str, str], str] = {}
        self._next: dict[str, int] = {}
        for placeholder, original in existing.items():
            m = _PLACEHOLDER.fullmatch(placeholder)
            if not m:
                continue
            etype, idx = m.group(1), int(m.group(2))
            self.by_value[(etype, original)] = placeholder
            self._next[etype] = max(self._next.get(etype, 0), idx + 1)

    def get(self, etype: str, original: str) -> str:
        key = (etype, original)
        if key not in self.by_value:
            idx = self._next.get(etype, 0)
            self._next[etype] = idx + 1
            self.by_value[key] = f"<{etype}_{idx}>"
        return self.by_value[key]


def mask_text(
    text: str, spans: Iterable[Span], placeholders: Placeholders
) -> tuple[str, dict[str, str]]:
    """Replace *spans* in *text*; return ``(masked_text, placeholder → original)``.

    Spans must not overlap each other. Spans that touch a placeholder already
    in the text are skipped — a value masked by an earlier pack stays masked
    under its first placeholder.
    """
    taken = [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
    chosen = sorted(
        (s for s in spans if not any(s.start < b and a < s.end for a, b in taken)),
        key=lambda s: s.start,
    )
    if not chosen:
        return text, {}
    # Allocate in reading order, then replace right-to-left so earlier
    # replacements don't shift later offsets.
    replacements = [
        (s.start, s.end, placeholders.get(s.entity_type, text[s.start : s.end])) for s in chosen
    ]
    partial = {ph: text[a:b] for a, b, ph in replacements}
    masked = text
    for start, end, placeholder in reversed(replacements):
        masked = masked[:start] + placeholder + masked[end:]
    return masked, partial


def mask_messages(
    state: RunState,
    find: Callable[[str], Sequence[Span]],
    node: str | None = None,
    stage: str = "ingress",
) -> RunStateDelta:
    """Mask every message in *state* with the spans *find* returns.

    Returns the delta for a masking node: new messages and the merged
    ``mask_map`` — or an empty delta when nothing was found. With *node*, the
    delta also records a ``sanitize`` verdict naming the masked entity types
    and counts (never the values: events go to the evidence ledger).
    """
    placeholders = Placeholders(state.mask_map)
    messages: list[Message] = []
    found: dict[str, str] = {}
    for msg in state.messages:
        masked, partial = mask_text(msg.content, find(msg.content), placeholders)
        messages.append(Message(role=msg.role, content=masked))
        found.update(partial)
    if not found:
        return RunStateDelta()
    new = {p: v for p, v in found.items() if p not in state.mask_map}
    events = [sanitize_event(node, stage, new)] if node and new else None
    return RunStateDelta(messages=messages, mask_map={**state.mask_map, **found}, events=events)


def sanitize_event(node: str, stage: str, masked: dict[str, str]) -> RunEvent:
    """A ``sanitize`` verdict for values replaced by placeholders — types and counts only."""
    counts: dict[str, int] = {}
    for placeholder in masked:
        m = _PLACEHOLDER.fullmatch(placeholder)
        etype = m.group(1) if m else placeholder
        counts[etype] = counts.get(etype, 0) + 1
    summary = ", ".join(f"{n} {etype}" for etype, n in sorted(counts.items()))
    return RunEvent(
        stage=stage,
        node=node,
        event_type="verdict",
        data={
            "verdict": "sanitize",
            "guard": node,
            "reason": f"masked {summary} — the model sees placeholders, never the values",
        },
    )


def unmask(text: str, mask_map: dict[str, str]) -> str:
    """Restore every placeholder in *text* from *mask_map*."""
    for placeholder, original in mask_map.items():
        text = text.replace(placeholder, original)
    return text


class UnmaskNode:
    """Egress node: restore masked values in the model's response.

    Any masking pack can place it in egress; running it twice is harmless.
    """

    name: str = "unmask"

    def __init__(self, name: str | None = None) -> None:
        if name is not None:
            self.name = name

    async def run(self, state: RunState) -> RunStateDelta:
        if not state.mask_map or state.response is None:
            return RunStateDelta()
        return RunStateDelta(response=unmask(state.response, state.mask_map))
