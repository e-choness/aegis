"""ContentNode — model-based labels and entity masking in one ingress step."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Mapping, Sequence

from aegis_core.masking import Found, mask_messages
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_pack_content.backend import Analysis, ContentModel


def entity_type(label: str) -> str:
    """Placeholder type for an entity label: "internal hostname" → ``INTERNAL_HOSTNAME``."""
    return "".join(c if c.isalnum() else "_" for c in label.strip().upper())


class ContentNode:
    """Ask a :class:`~aegis_pack_content.backend.ContentModel` about the request.

    - **Labels**: each classification task's answer for the latest user
      message goes to ``state.labels[task]``, its confidence to
      ``state.labels["<task>.confidence"]`` — for :mod:`aegis.policy
      <aegis_pack_classification.policy>` rules and residency's
      ``apply_when: sensitive``. The node itself never blocks.
    - **Entities**: spans of the configured entity types in any message are
      masked with the shared placeholder scheme (``<CREDENTIAL_0>``), next to
      whatever the PII pack masked; unmask on egress restores them.

    Analyses are cached per text, so earlier turns of a conversation aren't
    re-analysed on every request.
    """

    def __init__(
        self,
        model: ContentModel,
        entities: Mapping[str, str] | None = None,
        tasks: Mapping[str, Sequence[str]] | None = None,
        name: str = "content",
        cache_size: int = 256,
    ) -> None:
        self.name = name
        self.model = model
        self.entities = dict(entities or {})
        self.tasks = {k: list(v) for k, v in (tasks or {}).items()}
        self._cache: OrderedDict[str, Analysis] = OrderedDict()
        self._cache_size = cache_size

    def warmup(self) -> None:
        self.model.warmup()

    def _analyze(self, text: str) -> Analysis:
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        result = self.model.analyze(text, self.entities, self.tasks)
        self._cache[text] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    async def run(self, state: RunState) -> RunStateDelta:
        last_user = next((m.content for m in reversed(state.messages) if m.role == "user"), None)

        labels: dict[str, str] = {}
        if self.tasks and last_user is not None:
            analysis = await asyncio.to_thread(self._analyze, last_user)
            for task, answer in analysis.labels.items():
                labels[task] = answer.value
                labels[f"{task}.confidence"] = f"{answer.confidence:.3f}"

        delta = RunStateDelta()
        if self.entities:
            analyses = {
                m.content: await asyncio.to_thread(self._analyze, m.content) for m in state.messages
            }
            delta = mask_messages(
                state, lambda text: _non_overlapping(analyses[text]), node=self.name
            )

        new_placeholders = set(delta.mask_map or {}) - set(state.mask_map)
        masked = sorted({p.strip("<>").rsplit("_", 1)[0] for p in new_placeholders})
        event = RunEvent(
            stage="ingress",
            node=self.name,
            event_type="labels",
            data={
                "labels": {k: v for k, v in labels.items() if not k.endswith(".confidence")},
                "confidence": {
                    k.removesuffix(".confidence"): float(v)
                    for k, v in labels.items()
                    if k.endswith(".confidence")
                },
                "masked": masked,
            },
        )
        return RunStateDelta(
            labels=labels or None,
            messages=delta.messages,
            mask_map=delta.mask_map,
            events=[event, *(delta.events or [])],  # + a sanitize verdict if it masked
        )


def _non_overlapping(analysis: Analysis) -> list[Found]:
    """Spans to mask: most confident first, dropping any that overlap one already kept."""
    kept: list[Found] = []
    for e in sorted(analysis.entities, key=lambda e: (e.score, e.end - e.start), reverse=True):
        if not any(k.start < e.end and e.start < k.end for k in kept):
            kept.append(Found(e.start, e.end, entity_type(e.label), e.score))
    return kept
