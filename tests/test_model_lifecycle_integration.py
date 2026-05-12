"""Tests for ModelLifecycleManager integration with ExternalLLMProvider."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.aegis.services.model_lifecycle import ModelLifecycleManager, StatusSummary
from src.aegis.services.model_cache import ModelCache, ModelInfo
from src.aegis.services.tier2_failover import Tier2Failover, EndpointConfig


class TestModelLifecycleManager:
    """Test ModelLifecycleManager functionality."""

    def test_init_without_providers(self):
        """Test initialization without providers."""
        manager = ModelLifecycleManager()

        assert manager._external_llm is None
        assert manager._model_cache is None
        assert manager._discovery_status == "READY"

    def test_init_with_providers(self):
        """Test initialization with providers."""
        cache = ModelCache(ttl_seconds=300)
        external_llm = MagicMock()

        manager = ModelLifecycleManager(external_llm, cache)

        assert manager._external_llm == external_llm
        assert manager._model_cache == cache

    def test_declare_models(self):
        """Test declaring models by alias."""
        manager = ModelLifecycleManager()

        manager.declare_models("haiku", ["neural-chat-7b"])
        manager.declare_models("opus", ["neural-chat-13b"])

        assert manager._models_declared["haiku"] == ["neural-chat-7b"]
        assert manager._models_declared["opus"] == ["neural-chat-13b"]

    def test_get_availability(self):
        """Test getting endpoint availability."""
        manager = ModelLifecycleManager()

        manager._endpoint_health["http://localhost:8000"] = True
        manager._endpoint_health["http://localhost:8001"] = False

        availability = manager.get_availability()
        assert availability["http://localhost:8000"] is True
        assert availability["http://localhost:8001"] is False

    def test_get_failed_models(self):
        """Test getting failed models."""
        manager = ModelLifecycleManager()

        manager._failed_models.append("model-1: timeout")
        manager._failed_models.append("model-2: connection error")

        failed = manager.get_failed_models()
        assert len(failed) == 2
        assert "model-1" in failed[0]
        assert "model-2" in failed[1]

    def test_get_status_summary_without_cache(self):
        """Test status summary without cache."""
        manager = ModelLifecycleManager()

        summary = manager.get_status_summary()

        assert summary.model_discovery_status == "READY"
        assert summary.cache_staleness_seconds == 0
        assert summary.endpoint_health == {}

    def test_get_status_summary_with_cache(self):
        """Test status summary with cache."""
        cache = ModelCache(ttl_seconds=300)
        manager = ModelLifecycleManager(None, cache)

        # Set some cache data
        models = [ModelInfo(id="model-1", context_length=4096)]
        cache.set("tier_2", models)

        summary = manager.get_status_summary()

        assert summary.model_discovery_status == "READY"
        assert summary.cache_staleness_seconds == 0

    def test_get_status_summary_with_endpoint_health(self):
        """Test status summary includes endpoint health."""
        external_llm = MagicMock()
        external_llm._failover = MagicMock()
        external_llm._failover.get_status = MagicMock(return_value={
            "endpoints": {
                "http://localhost:8000": {"is_down": False},
                "http://localhost:8001": {"is_down": True},
            }
        })

        manager = ModelLifecycleManager(external_llm)

        summary = manager.get_status_summary()

        assert summary.endpoint_health["http://localhost:8000"] is True
        assert summary.endpoint_health["http://localhost:8001"] is False


@pytest.mark.asyncio
class TestModelLifecycleWarmup:
    """Test ModelLifecycleManager warmup process."""

    async def test_warmup_without_external_llm(self):
        """Test warmup when no external LLM provider is configured."""
        manager = ModelLifecycleManager()

        await manager.warmup()

        assert manager._discovery_status == "READY"

    async def test_warmup_with_healthy_provider(self):
        """Test warmup with healthy external LLM provider."""
        external_llm = AsyncMock()
        external_llm.health_check = AsyncMock(return_value=True)

        manager = ModelLifecycleManager(external_llm)

        await manager.warmup()

        assert manager._discovery_status == "READY"
        external_llm.health_check.assert_called_once()

    async def test_warmup_with_unhealthy_provider(self):
        """Test warmup with unhealthy external LLM provider."""
        external_llm = AsyncMock()
        external_llm.health_check = AsyncMock(return_value=False)

        manager = ModelLifecycleManager(external_llm)

        await manager.warmup()

        assert manager._discovery_status == "FAILED"
        assert len(manager._failed_models) > 0

    async def test_warmup_with_provider_exception(self):
        """Test warmup when provider raises exception."""
        external_llm = AsyncMock()
        external_llm.health_check = AsyncMock(side_effect=Exception("Connection failed"))

        manager = ModelLifecycleManager(external_llm)

        await manager.warmup()

        assert manager._discovery_status == "FAILED"
        assert len(manager._failed_models) > 0


class TestStatusSummary:
    """Test StatusSummary model."""

    def test_status_summary_creation(self):
        """Test creating status summary."""
        summary = StatusSummary(
            model_discovery_status="READY",
            cache_staleness_seconds=0,
            endpoint_health={"http://localhost:8000": True},
        )

        assert summary.model_discovery_status == "READY"
        assert summary.cache_staleness_seconds == 0
        assert summary.endpoint_health["http://localhost:8000"] is True

    def test_status_summary_with_circuit_breaker_state(self):
        """Test status summary with circuit breaker state."""
        summary = StatusSummary(
            model_discovery_status="READY",
            cache_staleness_seconds=10,
            endpoint_health={"http://localhost:8000": True},
            circuit_breaker_state={"http://localhost:8000": "HEALTHY"},
        )

        assert summary.circuit_breaker_state["http://localhost:8000"] == "HEALTHY"
