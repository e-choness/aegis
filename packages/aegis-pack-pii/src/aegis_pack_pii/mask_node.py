"""PiiMaskNode — replaces PII in messages with placeholders before the provider."""

from __future__ import annotations

import re
from typing import Any

from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.providers.models import Message
from aegis_pack_pii.detection import PiiDetector


class _Placeholders:
    """Allocates placeholders for one run.

    The same value always gets the same placeholder (so the model can tell
    that two mentions are the same person), numbering follows reading order,
    and placeholders already in the run's ``mask_map`` are reused, never
    reassigned to a different value.
    """

    def __init__(self, existing: dict[str, str]) -> None:
        self.by_value: dict[tuple[str, str], str] = {}
        self._next: dict[str, int] = {}
        for placeholder, original in existing.items():
            m = re.fullmatch(r"<([A-Z0-9_]+)_(\d+)>", placeholder)
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


def _mask_text(
    text: str,
    placeholders: _Placeholders,
    detector: PiiDetector,
) -> tuple[str, dict[str, str]]:
    """Mask PII entities in *text*.

    Returns ``(masked_text, partial_map)`` where ``partial_map`` maps each
    placeholder used in *text* to its original value.
    """
    found: list[Any] = sorted(detector.find(text), key=lambda r: r.start)
    if not found:
        return text, {}

    # Allocate in reading order, then replace right-to-left so earlier
    # replacements don't shift later offsets.
    spans = [(r.start, r.end, placeholders.get(r.entity_type, text[r.start : r.end])) for r in found]
    partial_map: dict[str, str] = {ph: text[a:b] for a, b, ph in spans}
    masked = text
    for start, end, placeholder in reversed(spans):
        masked = masked[:start] + placeholder + masked[end:]
    return masked, partial_map


class PiiMaskNode:
    """A :class:`~aegis_core.pipeline.protocol.PipelineNode` that masks PII in
    all messages before they reach the model.

    Placeholders (e.g. ``<EMAIL_ADDRESS_0>``) replace detected entities.
    The mapping of placeholder → original is stored in ``RunStateDelta.mask_map``
    and is NOT exposed in model-visible message content.

    Pair with :class:`~aegis_pack_pii.PiiUnmaskNode` in the egress stage to
    restore original values in the model's response.

    Requires the ``[pii]`` extra (``presidio-analyzer``, ``en_core_web_sm``).
    """

    name: str = "pii_mask_node"

    def __init__(self, name: str | None = None, detector: PiiDetector | None = None) -> None:
        if name is not None:
            self.name = name
        self._detector = detector or PiiDetector()

    async def run(self, state: RunState) -> RunStateDelta:
        """Mask PII in all messages; return updated messages and mask_map."""
        placeholders = _Placeholders(state.mask_map)
        new_messages: list[Message] = []
        accumulated_map: dict[str, str] = {}
        changed = False

        for msg in state.messages:
            masked_text, partial_map = _mask_text(msg.content, placeholders, self._detector)
            new_messages.append(Message(role=msg.role, content=masked_text))
            accumulated_map.update(partial_map)
            if partial_map:
                changed = True

        if not changed:
            return RunStateDelta()

        merged_map = {**state.mask_map, **accumulated_map}
        return RunStateDelta(messages=new_messages, mask_map=merged_map)
