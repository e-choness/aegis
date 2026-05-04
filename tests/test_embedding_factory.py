"""Tests for EmbeddingProviderFactory routing rules (ADR-008)."""
from __future__ import annotations
import pytest
from src.gateway.providers.embeddings.factory import EmbeddingProviderFactory
from src.gateway.providers.embeddings.vllm_embedding import VLLMEmbeddingProvider
from src.gateway.providers.embeddings.ollama_embedding import OllamaEmbeddingProvider
from src.gateway.providers.embeddings.openai_embedding import OpenAIEmbeddingProvider


class _MockHealth:
    def __init__(self, healthy: set[str]) -> None:
        self._healthy = healthy

    def is_healthy(self, provider: str) -> bool:
        return provider in self._healthy


class _AllHealthy(_MockHealth):
    def __init__(self):
        super().__init__({"vllm", "ollama", "openai"})


class _OnPremOnly(_MockHealth):
    def __init__(self):
        super().__init__({"vllm", "ollama"})


class _OllamaOnly(_MockHealth):
    def __init__(self):
        super().__init__({"ollama"})


# ── RESTRICTED ────────────────────────────────────────────────────────────────

def test_restricted_routes_to_vllm_when_healthy():
    provider = EmbeddingProviderFactory.get("RESTRICTED", _AllHealthy())
    assert isinstance(provider, VLLMEmbeddingProvider)


def test_restricted_falls_back_to_ollama_when_vllm_down():
    provider = EmbeddingProviderFactory.get("RESTRICTED", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)


def test_restricted_never_routes_to_openai():
    """HARD INVARIANT: RESTRICTED data must never reach a US-based cloud provider."""
    all_healthy = _AllHealthy()
    for _ in range(10):
        provider = EmbeddingProviderFactory.get("RESTRICTED", all_healthy)
        assert not isinstance(provider, OpenAIEmbeddingProvider), (
            "PIPEDA violation: RESTRICTED data routed to OpenAI"
        )


# ── CONFIDENTIAL ──────────────────────────────────────────────────────────────

def test_confidential_routes_to_vllm():
    provider = EmbeddingProviderFactory.get("CONFIDENTIAL", _AllHealthy())
    assert isinstance(provider, VLLMEmbeddingProvider)


def test_confidential_never_routes_to_openai():
    """CONFIDENTIAL also kept on-prem (internal tokens, API keys)."""
    all_healthy = _AllHealthy()
    provider = EmbeddingProviderFactory.get("CONFIDENTIAL", all_healthy)
    assert not isinstance(provider, OpenAIEmbeddingProvider)


def test_confidential_falls_back_to_ollama():
    provider = EmbeddingProviderFactory.get("CONFIDENTIAL", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)


# ── PUBLIC ────────────────────────────────────────────────────────────────────

def test_public_prefers_openai_when_key_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = EmbeddingProviderFactory.get("PUBLIC", _AllHealthy())
    assert isinstance(provider, OpenAIEmbeddingProvider)


def test_public_falls_back_to_vllm_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProviderFactory.get("PUBLIC", _OnPremOnly())
    assert isinstance(provider, VLLMEmbeddingProvider)


def test_public_falls_back_to_ollama_when_vllm_down(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProviderFactory.get("PUBLIC", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)


# ── INTERNAL ─────────────────────────────────────────────────────────────────

def test_internal_prefers_vllm():
    provider = EmbeddingProviderFactory.get("INTERNAL", _OnPremOnly())
    assert isinstance(provider, VLLMEmbeddingProvider)


def test_internal_falls_back_to_openai_when_vllm_down(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class OpenAIHealthy(_MockHealth):
        def __init__(self):
            super().__init__({"openai", "ollama"})

    provider = EmbeddingProviderFactory.get("INTERNAL", OpenAIHealthy())
    assert isinstance(provider, OpenAIEmbeddingProvider)


def test_internal_falls_back_to_ollama_when_all_cloud_down(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProviderFactory.get("INTERNAL", _OllamaOnly())
    assert isinstance(provider, OllamaEmbeddingProvider)


# ── No health checker (default behaviour) ─────────────────────────────────────

def test_no_health_checker_restricted_uses_vllm():
    """When no health_checker provided, factory assumes vllm and ollama are available."""
    provider = EmbeddingProviderFactory.get("RESTRICTED")
    assert isinstance(provider, VLLMEmbeddingProvider)
