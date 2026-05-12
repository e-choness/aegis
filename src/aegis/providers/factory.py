from __future__ import annotations
import os
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .azure_openai_provider import AzureOpenAIProvider
from .ollama_provider import OllamaProvider


class ProviderFactory:
    """Returns the correct LLMProvider for a given provider name.

    Supported providers: anthropic, azure_openai, ollama, external_llm

    Pattern: Provider-agnostic interface (LLMProvider ABC) allows swapping
    providers without touching application code. Config-driven model registry
    (model_registry.yaml) decouples model IDs from code.

    Similar to OpenClaude: all configuration external, providers pluggable.
    """

    @staticmethod
    def get(provider: str) -> LLMProvider:
        if provider == "anthropic":
            return AnthropicProvider()
        if provider == "azure_openai":
            return AzureOpenAIProvider()
        if provider == "ollama":
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            return OllamaProvider(base_url=base_url)
        if provider == "external_llm":
            # External LLM provider is initialized by main.py and stored in app state
            # This is a placeholder that should not be called directly
            raise RuntimeError(
                "external_llm provider must be initialized in app state by main.py. "
                "Use request.app.state.external_llm_provider instead."
            )
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            "Supported: anthropic, azure_openai, ollama, external_llm."
        )
