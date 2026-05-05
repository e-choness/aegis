"""Tests for EmbeddingProviderFactory routing rules (ADR-008)."""
from __future__ import annotations
import pytest
from unittest.mock import Mock
from src.gateway.providers.embeddings.factory import EmbeddingProviderFactory
from src.gateway.providers.embeddings.ollama_embedding import OllamaEmbeddingProvider
from src.gateway.providers.embeddings.openai_embedding import OpenAIEmbeddingProvider


class _AllHealthy:
    def is_healthy(self, provider: str) -> bool:
        return True


class _OllamaOnly:
    def is_healthy(self, provider: str) -> bool:
        return provider == "ollama"


class _OpenAIOnly:
    def is_healthy(self, provider: str) -> bool:
        return provider == "openai"


# -- RESTRICTED ----------------------------------------------------------------

def test_restricted_routes_to_ollama_when_healthy():
    """RESTRICTED data routes to Ollama (no vLLM in simplified architecture)."""
    provider = EmbeddingProviderFactory.get("RESTRICTED", _AllHealthy())
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.dimensions == 768

def test_restricted_falls_back_to_ollama_when_vllm_down():
    provider = EmbeddingProviderFactory.get("RESTRICTED", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)

def test_restricted_never_routes_to_openai():
    """HARD INVARIANT: RESTRICTED data must never reach a US-based cloud provider."""
    all_healthy = _AllHealthy()
    provider = EmbeddingProviderFactory.get("RESTRICTED", all_healthy)
    assert not isinstance(
        provider, OpenAIEmbeddingProvider
    ), "PIPEDA violation: RESTRICTED data routed to OpenAI"


# -- CONFIDENTIAL --------------------------------------------------------------

def test_confidential_routes_to_ollama():
    provider = EmbeddingProviderFactory.get("CONFIDENTIAL", _AllHealthy())
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.dimensions == 768


# -- PUBLIC -------------------------------------------------------------------

def test_public_uses_openai_when_healthy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = EmbeddingProviderFactory.get("PUBLIC", _AllHealthy())
    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.dimensions == 1536

def test_public_falls_back_to_ollama_when_openai_unavailable(monkeypatch):
    """Without OPENAI_API_KEY, PUBLIC routes to Ollama."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProviderFactory.get("PUBLIC", None)
    assert isinstance(provider, OllamaEmbeddingProvider)

def test_public_falls_back_to_ollama_when_ollama_down(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = EmbeddingProviderFactory.get("PUBLIC", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)


# -- INTERNAL ------------------------------------------------------------------

def test_internal_prefers_openai_when_healthy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = EmbeddingProviderFactory.get("INTERNAL", _AllHealthy())
    assert isinstance(provider, OpenAIEmbeddingProvider)

def test_internal_falls_back_to_ollama_when_openai_down(monkeypatch):
    """Without OPENAI_API_KEY, INTERNAL routes to Ollama."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProviderFactory.get("INTERNAL", None)
    assert isinstance(provider, OllamaEmbeddingProvider)


# -- No Health Checker --------------------------------------------------------

def test_no_health_checker_restricted_uses_ollama():
    """When no health_checker provided, factory uses Ollama for RESTRICTED."""
    provider = EmbeddingProviderFactory.get("RESTRICTED")
    assert isinstance(provider, OllamaEmbeddingProvider)
