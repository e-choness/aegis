from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


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
