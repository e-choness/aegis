from __future__ import annotations
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Abstract base for all embedding providers.
    ADR-008: 768-dim is canonical for RESTRICTED/CONFIDENTIAL data.
    Never mix dimensions within a single pgvector index.
    """

    dimensions: int  # subclasses declare this as a class attribute

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
