"""PiiMaskNode — replaces PII in messages with placeholders before the provider."""

from __future__ import annotations

from typing import Any

from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.providers.models import Message


def _deduplicate(results: list[Any]) -> list[Any]:
    """Remove entities whose span is fully contained within a larger entity.

    Presidio may return overlapping results (e.g. EMAIL_ADDRESS + URL for the
    same text span).  We keep the widest entity and discard sub-spans so that
    right-to-left replacement stays positionally valid.
    """
    sorted_r: list[Any] = sorted(
        results, key=lambda r: r.end - r.start, reverse=True
    )
    kept: list[Any] = []
    for r in sorted_r:
        s: int = r.start
        e: int = r.end
        if not any(k.start <= s and k.end >= e for k in kept):
            kept.append(r)
    return kept


def _mask_text(
    text: str,
    type_counts: dict[str, int],
) -> tuple[str, dict[str, str]]:
    """Mask PII entities in *text* using Presidio.

    Args:
        text: The text to scan.
        type_counts: Mutable dict tracking per-entity-type counter across
            multiple messages (so placeholders are unique per run).

    Returns:
        A tuple ``(masked_text, partial_map)`` where ``partial_map`` maps
        each new ``<ENTITY_TYPE_N>`` placeholder to its original value.
    """
    from aegis_pack_pii._engine import get_analyzer

    analyzer = get_analyzer()
    results: list[Any] = analyzer.analyze(text=text, language="en")
    if not results:
        return text, {}

    # Remove sub-span duplicates before replacing.
    deduped: list[Any] = _deduplicate(results)

    partial_map: dict[str, str] = {}
    masked = text
    # Process right-to-left so earlier-position replacements don't shift later ones.
    for result in sorted(deduped, key=lambda r: r.start, reverse=True):
        etype: str = result.entity_type
        idx = type_counts.get(etype, -1) + 1
        type_counts[etype] = idx
        placeholder = f"<{etype}_{idx}>"
        start: int = result.start
        end: int = result.end
        original = text[start:end]
        partial_map[placeholder] = original
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

    async def run(self, state: RunState) -> RunStateDelta:
        """Mask PII in all messages; return updated messages and mask_map."""
        type_counts: dict[str, int] = {}
        new_messages: list[Message] = []
        accumulated_map: dict[str, str] = {}
        changed = False

        for msg in state.messages:
            masked_text, partial_map = _mask_text(msg.content, type_counts)
            new_messages.append(Message(role=msg.role, content=masked_text))
            accumulated_map.update(partial_map)
            if partial_map:
                changed = True

        if not changed:
            return RunStateDelta()

        merged_map = {**state.mask_map, **accumulated_map}
        return RunStateDelta(messages=new_messages, mask_map=merged_map)
