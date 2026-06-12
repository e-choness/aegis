"""ModelProvider Protocol — the public contract for all provider implementations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from aegis_core.providers.models import (
    Chunk,
    CompletionRequest,
    CompletionResult,
    ProviderInfo,
)


@runtime_checkable
class ModelProvider(Protocol):
    """Contract for all Aegis model providers.

    Implementations must be importable via the ``aegis.providers`` entry-point
    group and registered in the plugin registry.  Third-party providers follow
    the same contract (PROJECT_SPEC §4).
    """

    name: str

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        """Return a single completion for *req*."""
        ...

    async def stream(self, req: CompletionRequest) -> AsyncIterator[Chunk]:
        """Yield token chunks for *req* as they arrive."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return an embedding vector per text in *texts*."""
        ...

    def info(self) -> ProviderInfo:
        """Return static metadata (models, residency, capabilities)."""
        ...
