"""Provider data models — request/response/info types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    """A request to a ModelProvider's complete() or stream() method."""

    messages: list[Message]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class UsageInfo:
    """Token and cost accounting for a completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


@dataclass
class CompletionResult:
    """Result returned from ModelProvider.complete()."""

    text: str
    model: str
    usage: UsageInfo
    finish_reason: str = "stop"


@dataclass
class Chunk:
    """A single token/delta from a streaming completion."""

    text: str
    finish_reason: str | None = None


@dataclass
class ResidencyInfo:
    """Declared geographic residency for a provider endpoint."""

    region: str = ""
    jurisdiction: str = ""
    source_url: str = ""


@dataclass
class ProviderInfo:
    """Static metadata about a ModelProvider instance."""

    name: str
    provider_type: str  # e.g. "anthropic", "openai_compatible"
    models: list[str]
    residency: ResidencyInfo
    supports_streaming: bool = True
    supports_embeddings: bool = False
