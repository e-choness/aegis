from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("aegis.tier2_failover")


@dataclass
class EndpointConfig:
    """Configuration for a Tier 2 endpoint."""
    url: str
    weight: int = 1


@dataclass
class EndpointState:
    """Tracks health and circuit breaker state of an endpoint."""
    url: str
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    is_down: bool = False
    down_until: Optional[float] = None
    request_count: int = 0
    failure_count: int = 0


class CircuitBreakerState:
    """Enum-like states for circuit breaker."""
    HEALTHY = "HEALTHY"
    OPEN = "OPEN"  # Failures exceeded, endpoint DOWN
    HALF_OPEN = "HALF_OPEN"  # Recovery attempt in progress


class Tier2Failover:
    """
    Load balancing, failover logic, and circuit breaker for Tier 2 endpoints.
    - Round-robin distribution with weights
    - Automatic failover to next endpoint on timeout/error
    - Circuit breaker: 3 failures → DOWN for 60s
    """

    def __init__(
        self,
        endpoints: List[EndpointConfig],
        timeout_seconds: float = 5.0,
        circuit_breaker_failures: int = 3,
        circuit_breaker_recovery_seconds: int = 60,
    ):
        self._endpoints = {ep.url: EndpointState(url=ep.url) for ep in endpoints}
        self._endpoint_weights = {ep.url: ep.weight for ep in endpoints}
        self._timeout_seconds = timeout_seconds
        self._circuit_breaker_failures = circuit_breaker_failures
        self._circuit_breaker_recovery_seconds = circuit_breaker_recovery_seconds
        self._round_robin_index = 0
        self._failover_count = 0

        logger.info(
            "Tier2Failover initialized with %d endpoints, timeout=%fs, "
            "breaker_failures=%d, recovery=%ds",
            len(endpoints),
            timeout_seconds,
            circuit_breaker_failures,
            circuit_breaker_recovery_seconds,
        )

    async def select_endpoint(self) -> Optional[str]:
        """
        Round-robin with weighted distribution; skip DOWN endpoints.
        Returns URL of next healthy endpoint or None if all are down.
        """
        healthy_endpoints = [
            url for url, state in self._endpoints.items() if not state.is_down
        ]

        if not healthy_endpoints:
            logger.warning("No healthy endpoints available")
            return None

        # Simple round-robin (could be weighted in production)
        selected = healthy_endpoints[self._round_robin_index % len(healthy_endpoints)]
        self._round_robin_index += 1
        logger.debug("Selected endpoint via round-robin: %s", selected)
        return selected

    def mark_endpoint_failed(self, endpoint_url: str) -> None:
        """Record failure for circuit breaker logic."""
        if endpoint_url not in self._endpoints:
            return

        state = self._endpoints[endpoint_url]
        state.consecutive_failures += 1
        state.failure_count += 1
        state.last_failure_time = time.time()

        logger.warning(
            "Endpoint %s marked FAILED (consecutive=%d)",
            endpoint_url,
            state.consecutive_failures,
        )

        # Check if we should open circuit breaker
        if state.consecutive_failures >= self._circuit_breaker_failures:
            state.is_down = True
            state.down_until = time.time() + self._circuit_breaker_recovery_seconds
            logger.error(
                "Circuit breaker OPEN for %s (failures=%d, down_until=%s)",
                endpoint_url,
                state.consecutive_failures,
                state.down_until,
            )

    def mark_endpoint_healthy(self, endpoint_url: str) -> None:
        """Clear failures on success."""
        if endpoint_url not in self._endpoints:
            return

        state = self._endpoints[endpoint_url]
        state.consecutive_failures = 0
        state.last_failure_time = None
        state.request_count += 1

        # Check if we should close circuit breaker (recovery from DOWN)
        if state.is_down and state.down_until and time.time() >= state.down_until:
            state.is_down = False
            state.down_until = None
            logger.info("Circuit breaker CLOSED for %s (recovery successful)", endpoint_url)
        elif not state.is_down:
            logger.debug("Endpoint %s marked HEALTHY", endpoint_url)

    def get_circuit_breaker_state(self, endpoint_url: str) -> str:
        """Get current circuit breaker state."""
        if endpoint_url not in self._endpoints:
            return CircuitBreakerState.HEALTHY

        state = self._endpoints[endpoint_url]
        if state.is_down:
            if state.down_until and time.time() >= state.down_until:
                return CircuitBreakerState.HALF_OPEN
            return CircuitBreakerState.OPEN

        return CircuitBreakerState.HEALTHY

    def reset_circuit_breaker(self, endpoint_url: str) -> bool:
        """Manually reset circuit breaker for an endpoint."""
        if endpoint_url not in self._endpoints:
            return False

        state = self._endpoints[endpoint_url]
        state.is_down = False
        state.consecutive_failures = 0
        state.down_until = None
        logger.info("Circuit breaker RESET for %s", endpoint_url)
        return True

    def get_status(self) -> dict:
        """Get current failover status."""
        return {
            "total_failovers": self._failover_count,
            "endpoints": {
                url: {
                    "is_down": state.is_down,
                    "consecutive_failures": state.consecutive_failures,
                    "request_count": state.request_count,
                    "failure_count": state.failure_count,
                    "circuit_breaker_state": self.get_circuit_breaker_state(url),
                }
                for url, state in self._endpoints.items()
            },
        }

    def increment_failover_count(self) -> None:
        """Track number of failovers."""
        self._failover_count += 1
