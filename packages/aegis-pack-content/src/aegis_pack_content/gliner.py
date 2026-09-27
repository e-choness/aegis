"""GLiNER2 backend — zero-shot entities and classification from one small encoder."""

from __future__ import annotations

import importlib.util
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from aegis_pack_content.backend import Analysis, Entity, Label

DEFAULT_MODEL = "fastino/gliner2-base-v1"
INSTALL_HINT = (
    'pip install "aegis-gateway-pack-content[model]"  '
    "(CPU-only: pip install torch --index-url https://download.pytorch.org/whl/cpu first)"
)


def ensure_installed() -> None:
    """Raise ``ValueError`` with the install command if ``gliner2`` is missing."""
    if importlib.util.find_spec("gliner2") is None:
        raise ValueError(f"the gliner2 backend needs the [model] extra — {INSTALL_HINT}")


class Gliner2Model:
    """:class:`~aegis_pack_content.backend.ContentModel` backed by GLiNER2.

    Args:
        model_id: Hugging Face model id or local path. Downloaded on first
            load unless already cached (bake it into images; see the docs).
        options: ``threshold`` (0-1, default 0.5) — minimum entity confidence.
    """

    def __init__(
        self, model_id: str = DEFAULT_MODEL, options: Mapping[str, Any] | None = None
    ) -> None:
        self.model_id = model_id
        self.threshold = float((options or {}).get("threshold", 0.5))
        self._model: Any = None
        self._lock = threading.Lock()

    def warmup(self) -> None:
        with self._lock:
            if self._model is None:
                from gliner2 import GLiNER2  # type: ignore[import-not-found]

                self._model = GLiNER2.from_pretrained(self.model_id)

    def analyze(
        self,
        text: str,
        entities: Mapping[str, str],
        tasks: Mapping[str, Sequence[str]],
    ) -> Analysis:
        self.warmup()
        schema = self._model.create_schema()
        if entities:
            schema = schema.entities(dict(entities))
        for task, values in tasks.items():
            schema = schema.classification(task, list(values))
        with self._lock:  # one inference at a time: the model isn't thread-safe
            raw = self._model.extract(
                text,
                schema,
                threshold=self.threshold,
                include_confidence=True,
                include_spans=True,
            )
        return _parse(raw, tasks)


def _parse(raw: Mapping[str, Any], tasks: Mapping[str, Sequence[str]]) -> Analysis:
    found = [
        Entity(int(hit["start"]), int(hit["end"]), label, float(hit.get("confidence", 1.0)))
        for label, hits in (raw.get("entities") or {}).items()
        for hit in hits or []
        if isinstance(hit, Mapping) and "start" in hit and "end" in hit
    ]
    labels: dict[str, Label] = {}
    for task in tasks:
        answer = raw.get(task)
        if isinstance(answer, Mapping) and "label" in answer:
            labels[task] = Label(str(answer["label"]), float(answer.get("confidence", 1.0)))
        elif isinstance(answer, str):
            labels[task] = Label(answer, 1.0)
    return Analysis(entities=found, labels=labels)
