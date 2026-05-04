from __future__ import annotations
import logging
import os
from typing import Optional
from ..base import LLMProvider  # noqa: F401 (re-exported for convenience)
from .base import EmbeddingProvider
from .vllm_embedding import VLLMEmbeddingProvider
from .ollama_embedding import OllamaEmbeddingProvider
from .openai_embedding import OpenAIEmbeddingProvider

logger = logging.getLogger("aegis.embedding.factory")


class EmbeddingProviderFactory:
    """
    Routes embedding requests by data classification + provider health.

    ADR-008: 768-dim is canonical for RESTRICTED/CONFIDENTIAL.
    HARD INVARIANT: RESTRICTED data NEVER reaches OpenAI (US-based).
    NEVER mix dimensions within a single pgvector index.

    Routing table (per spec):
      RESTRICTED   → vLLM (768) else Ollama (768)     [cloud FORBIDDEN]
      CONFIDENTIAL → vLLM (768) else Ollama (768)     [OpenAI is US-based, avoid]
      INTERNAL     → vLLM (768) else OpenAI (1536*) else Ollama (768)
      PUBLIC       → OpenAI (1536*) else vLLM (768) else Ollama (768)

    * PUBLIC/INTERNAL using OpenAI returns 1536-dim; callers must use a
      separate 1536-dim index (never mix with 768-dim index).
    """

    @staticmethod
    def get(
        data_classification: str,
        health_checker=None,
    ) -> EmbeddingProvider:
        def healthy(provider: str) -> bool:
            if health_checker is None:
                return provider in ("vllm", "ollama")
            return health_checker.is_healthy(provider)

        if data_classification in ("RESTRICTED", "CONFIDENTIAL"):
            # Cloud providers FORBIDDEN for RESTRICTED.
            # CONFIDENTIAL also kept on-prem (internal emails, API keys, tokens).
            if healthy("vllm"):
                return VLLMEmbeddingProvider()
            return OllamaEmbeddingProvider()

        # INTERNAL or PUBLIC
        if data_classification == "PUBLIC":
            if healthy("openai") and os.environ.get("OPENAI_API_KEY"):
                return OpenAIEmbeddingProvider()
            if healthy("vllm"):
                return VLLMEmbeddingProvider()
            return OllamaEmbeddingProvider()

        # INTERNAL — prefer on-prem for cost, fall back to OpenAI
        if healthy("vllm"):
            return VLLMEmbeddingProvider()
        if healthy("openai") and os.environ.get("OPENAI_API_KEY"):
            return OpenAIEmbeddingProvider()
        return OllamaEmbeddingProvider()
