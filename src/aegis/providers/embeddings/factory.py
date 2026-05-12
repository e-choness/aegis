from __future__ import annotations
import logging
import os
from typing import Optional
from ..base import LLMProvider  # noqa: F401 (re-exported for convenience)
from .base import EmbeddingProvider
from .ollama_embedding import OllamaEmbeddingProvider
from .openai_embedding import OpenAIEmbeddingProvider

logger = logging.getLogger("aegis.embedding.factory")


class EmbeddingProviderFactory:
    """
    Routes embedding requests by data classification + provider health.

    Simplified architecture (no vLLM):
    - RESTRICTED/CONFIDENTIAL: Ollama only (768-dim nomic-embed-text)
    - INTERNAL: Ollama preferred, OpenAI (1536-dim*) optional for enhanced capacity
    - PUBLIC: OpenAI preferred, Ollama fallback

    * OpenAI 1536-dim uses a SEPARATE pgvector index — never mixed with 768-dim.
    """

    @staticmethod
    def get(
        data_classification: str,
        health_checker=None,
    ) -> EmbeddingProvider:
        def healthy(provider: str) -> bool:
            if health_checker is None:
                # Default: assume Ollama is always healthy (local/offline)
                # OpenAI is healthy only if API key is configured
                if provider == "ollama":
                    return True
                if provider == "openai":
                    return bool(os.environ.get("OPENAI_API_KEY"))
                return False
            return health_checker.is_healthy(provider)

        if data_classification in ("RESTRICTED", "CONFIDENTIAL"):
            # Cloud providers are forbidden for sensitive data.
            # Ollama provides 768-dim embeddings for local processing.
            return OllamaEmbeddingProvider()

        # INTERNAL or PUBLIC
        if data_classification == "PUBLIC":
            if healthy("openai"):
                return OpenAIEmbeddingProvider()
            return OllamaEmbeddingProvider()

        # INTERNAL — prefer Ollama for zero cost, OpenAI optional for higher capacity
        if healthy("openai"):
            return OpenAIEmbeddingProvider()
        return OllamaEmbeddingProvider()
