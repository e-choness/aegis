"""StubModel — a content backend with no model, for tests, CI and offline runs.

It finds no entities and answers every classification task with its *first*
value (list the benign value first — ``[normal request, prompt injection …]``
— and the stub never flags anything). Select it with ``backend: stub``, or
without touching the config::

    AEGIS__GUARDRAILS__<NAME>__BACKEND=stub aegis serve …
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aegis_pack_content.backend import Analysis, Label


class StubModel:
    def __init__(
        self, model_id: str | None = None, options: Mapping[str, Any] | None = None
    ) -> None:
        self.model_id = model_id

    def warmup(self) -> None:
        pass

    def analyze(
        self, text: str, entities: Mapping[str, str], tasks: Mapping[str, Sequence[str]]
    ) -> Analysis:
        return Analysis(labels={task: Label(values[0], 1.0) for task, values in tasks.items()})
