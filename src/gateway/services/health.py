from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("aegis.health")

POLL_INTERVAL_SECONDS = 30
CIRCUIT_OPEN_THRESHOLD = 3
CIRCUIT_RESET_SECONDS = 60


class ProviderHealth:
    def __init__(self) -> None:
        self._healthy: dict[str, bool] = {
            "anthropic": True,
            "azure_openai": True,
            "vllm": True,
            "ollama": True,
        }
        self._failures: dict[str, int] = {k: 0 for k in self._healthy}
        self._circuit_open_at: dict[str, Optional[float]] = {k: None for k in self._healthy}

    def is_healthy(self, provider: str) -> bool:
        open_at = self._circuit_open_at.get(provider)
        if open_at is not None:
            if time.monotonic() - open_at > CIRCUIT_RESET_SECONDS:
                # Half-open: try again
                self._circuit_open_at[provider] = None
                self._failures[provider] = 0
                return True
            return False
        return self._healthy.get(provider, False)

    def record_success(self, provider: str) -> None:
        self._healthy[provider] = True
        self._failures[provider] = 0
        self._circuit_open_at[provider] = None

    def record_failure(self, provider: str) -> None:
        self._failures[provider] = self._failures.get(provider, 0) + 1
        if self._failures[provider] >= CIRCUIT_OPEN_THRESHOLD:
            if self._circuit_open_at.get(provider) is None:
                logger.warning("Circuit breaker OPEN for provider=%s", provider)
                self._circuit_open_at[provider] = time.monotonic()
            self._healthy[provider] = False

    def status(self) -> dict[str, bool]:
        return {p: self.is_healthy(p) for p in self._healthy}


class AlwaysHealthyChecker:
    """Test double — all providers healthy."""

    def is_healthy(self, provider: str) -> bool:
        return True
