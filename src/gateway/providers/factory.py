from __future__ import annotations
import os
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider
from .azure_openai_provider import AzureOpenAIProvider
from .ollama_provider import OllamaProvider
from .vllm_provider import VLLMProvider


class ProviderFactory:
    """Returns the correct LLMProvider for a given provider name."""

    @staticmethod
    def get(provider: str) -> LLMProvider:
        if provider == "anthropic":
            return AnthropicProvider()
        if provider == "azure_openai":
            return AzureOpenAIProvider()
        if provider == "ollama":
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            return OllamaProvider(base_url=base_url)
        if provider == "vllm":
            base_url = os.environ.get("VLLM_BASE_URL", "http://vllm:8001")
            return VLLMProvider(base_url=base_url)
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            "Supported: anthropic, azure_openai, ollama, vllm."
        )
