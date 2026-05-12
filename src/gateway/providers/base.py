from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator, Optional


@dataclass
class CompletionRequest:
    model_id: str
    prompt: str
    system_prompt: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.2
    use_cache: bool = True


@dataclass
class CompletionResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool = False
    model_id: str = ""


class ModelStatus(str, Enum):
    """Model availability status."""
    READY = "READY"
    WARMING = "WARMING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class LLMProvider(ABC):
    """Abstract base for all LLM providers. Application code never imports concrete classes."""

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        ...

    @abstractmethod
    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    async def pull_model(self, model_id: str) -> AsyncGenerator[str, None]:
        """Pull/download a model. Stub for cloud providers (no-op), overridden by local providers."""
        yield "model already available"

    async def get_model_status(self, model_id: str) -> ModelStatus:
        """Check if model is available. Default to READY for cloud providers."""
        return ModelStatus.READY
