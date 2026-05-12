from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("aegis.model_cache")


@dataclass
class ModelInfo:
    """Model metadata from Tier 2 discovery."""
    id: str
    context_length: int
    supports_function_calling: bool = False
    estimated_cost_per_mtok: float = 0.0


@dataclass
class ModelList:
    """Cached model list with timestamp."""
    models: list[ModelInfo]
    timestamp: float


class ModelCache:
    """
    In-memory TTL-based cache for model discovery (/v1/models endpoint).
    Stores provider model lists with timestamp for staleness checking.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._ttl_seconds = ttl_seconds
        self._cache: Dict[str, ModelList] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("ModelCache initialized with TTL=%ds", ttl_seconds)

    def get(self, provider: str) -> Optional[ModelList]:
        """Retrieve cached model list if exists and not stale."""
        if provider not in self._cache:
            self._cache_misses += 1
            return None

        cached = self._cache[provider]
        if self.is_stale(provider):
            logger.debug("Cache HIT but STALE for provider=%s", provider)
            self._cache_misses += 1
            return None

        logger.debug("Cache HIT for provider=%s", provider)
        self._cache_hits += 1
        return cached

    def set(self, provider: str, models: list[ModelInfo]) -> None:
        """Cache model list with current timestamp."""
        self._cache[provider] = ModelList(models=models, timestamp=time.time())
        logger.info("Cache SET for provider=%s, count=%d", provider, len(models))

    def is_stale(self, provider: str) -> bool:
        """Check if cache entry is beyond TTL."""
        if provider not in self._cache:
            return True

        cached = self._cache[provider]
        age = time.time() - cached.timestamp
        return age > self._ttl_seconds

    def invalidate(self, provider: str) -> None:
        """Force cache invalidation for a provider."""
        if provider in self._cache:
            del self._cache[provider]
            logger.info("Cache INVALIDATE for provider=%s", provider)

    def get_staleness_seconds(self, provider: str) -> int:
        """How long past TTL the cache is (negative if still fresh)."""
        if provider not in self._cache:
            return -1

        cached = self._cache[provider]
        age = time.time() - cached.timestamp
        return max(0, int(age - self._ttl_seconds))

    def get_metrics(self) -> Dict[str, int]:
        """Return cache hit/miss metrics."""
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cached_providers": len(self._cache),
        }
