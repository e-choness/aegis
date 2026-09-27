"""The model interface the content pack runs on — swap the model, keep the pack."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Entity:
    """A span the model found: ``text[start:end]`` is a *label*."""

    start: int
    end: int
    label: str
    score: float


@dataclass(frozen=True)
class Label:
    """The model's answer to one classification task."""

    value: str
    confidence: float


@dataclass(frozen=True)
class Analysis:
    entities: list[Entity] = field(default_factory=list)
    labels: dict[str, Label] = field(default_factory=dict)


@runtime_checkable
class ContentModel(Protocol):
    """What the pack needs from a model: entities and labels for one text, in one call.

    *entities* maps each entity label to a short description ("credential" →
    "password, token, API key or other secret"); *tasks* maps each
    classification task to its allowed values. Implementations are called
    from a worker thread, one call at a time.
    """

    def analyze(
        self,
        text: str,
        entities: Mapping[str, str],
        tasks: Mapping[str, Sequence[str]],
    ) -> Analysis: ...

    def warmup(self) -> None:
        """Load weights now rather than on the first request."""
        ...
