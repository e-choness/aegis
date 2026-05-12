from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("aegis.model_lifecycle")


@dataclass
class StatusSummary:
    """Overall model discovery and tier status."""
    model_discovery_status: str  # READY, WARMING, FAILED
    cache_staleness_seconds: int
    endpoint_health: Dict[str, bool]
    circuit_breaker_state: Dict[str, str] = None


class ModelLifecycleManager:
    """
    Model availability checking and status tracking (no model pulling).
    Manages model availability across all tiers without downloading.
    Works with ExternalLLMProvider for Tier 2 and ModelCache for caching.
    """

    def __init__(self, external_llm_provider=None, model_cache=None):
        self._external_llm = external_llm_provider
        self._model_cache = model_cache
        self._models_declared = {}  # alias -> [model_ids]
        self._endpoint_health = {}  # endpoint_url -> bool
        self._failed_models = []
        self._discovery_status = "READY"
        logger.info("ModelLifecycleManager initialized")

    def declare_models(self, alias: str, model_ids: List[str]) -> None:
        """
        Instant registration of models from config (no network calls).
        Stores models by alias for later discovery/health checking.
        """
        try:
            self._models_declared[alias] = model_ids
            logger.info("Declared %d models for alias=%s", len(model_ids), alias)
        except Exception as e:
            logger.error("Error declaring models for %s: %s", alias, e)
            self._failed_models.append(f"{alias}: {str(e)}")

    async def warmup(self) -> None:
        """
        Health checks only on all configured endpoints (no model downloads).
        Calls health_check() on ExternalLLMProvider if configured.
        """
        logger.info("Starting model warmup (health checks only)")
        self._discovery_status = "WARMING"

        try:
            if not self._external_llm:
                logger.info("Warmup: no external LLM provider configured")
                self._discovery_status = "READY"
                return

            # Call health check on external LLM provider
            is_healthy = await self._external_llm.health_check()
            if is_healthy:
                logger.info("Warmup: external LLM provider health check PASSED")
                self._discovery_status = "READY"
            else:
                logger.warning("Warmup: external LLM provider health check FAILED")
                self._discovery_status = "FAILED"
                self._failed_models.append("external LLM health check failed")

        except asyncio.CancelledError:
            logger.warning("Warmup: cancelled")
            raise
        except Exception as e:
            logger.warning("Warmup encountered error: %s", e)
            self._discovery_status = "FAILED"
            self._failed_models.append(str(e))

    def get_availability(self) -> Dict[str, bool]:
        """Current endpoint availability status."""
        return self._endpoint_health.copy()

    def get_failed_models(self) -> List[str]:
        """Models/endpoints that failed during warmup."""
        return self._failed_models.copy()

    def get_status_summary(self) -> StatusSummary:
        """Returns overall health for /api/v1/health endpoint."""
        cache_staleness = 0
        if self._model_cache:
            cache_staleness = self._model_cache.get_staleness_seconds("tier_2")

        endpoint_health = {}
        if self._external_llm and hasattr(self._external_llm, '_failover'):
            failover_status = self._external_llm._failover.get_status()
            for url, state in failover_status.get("endpoints", {}).items():
                endpoint_health[url] = not state.get("is_down", False)

        return StatusSummary(
            model_discovery_status=self._discovery_status,
            cache_staleness_seconds=cache_staleness,
            endpoint_health=endpoint_health,
            circuit_breaker_state={}
        )
