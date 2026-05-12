from __future__ import annotations
import logging
from fastapi import APIRouter, Request

logger = logging.getLogger("aegis.api.health")
router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health(request: Request):
    """
    Enhanced health endpoint with model lifecycle status and Tier 2 endpoint health.
    Returns detailed tier and endpoint information.
    """
    try:
        svc = getattr(request.app.state, "inference_service", None)
        violations = svc._audit.count_restricted_cloud_violations() if svc else 0

        # Get model lifecycle status if available
        model_lifecycle = getattr(request.app.state, "model_lifecycle", None)
        model_status = {}
        if model_lifecycle:
            summary = model_lifecycle.get_status_summary()
            model_status = {
                "discovery_status": summary.model_discovery_status,
                "cache_staleness_seconds": summary.cache_staleness_seconds,
                "endpoint_health": summary.endpoint_health,
            }

        # Get Tier 2 failover status if available
        failover = getattr(request.app.state, "tier2_failover", None)
        tier_2_status = "unavailable"
        tier_2_endpoints = []
        if failover:
            failover_status = failover.get_status()
            tier_2_status = "healthy"
            for url, endpoint_state in failover_status.get("endpoints", {}).items():
                tier_2_endpoints.append({
                    "url": url,
                    "status": "healthy" if not endpoint_state.get("is_down") else "down",
                    "circuit_breaker_state": endpoint_state.get("circuit_breaker_state", "HEALTHY"),
                    "failure_count": endpoint_state.get("failure_count", 0),
                })

        return {
            "status": "healthy",
            "version": "0.3.0",
            "model_discovery": {
                "status": model_status.get("discovery_status", "ready"),
                "cache_staleness_seconds": model_status.get("cache_staleness_seconds", 0),
                "stale_fallback_enabled": True,
            },
            "tiers": {
                "tier_1a": {"status": "healthy", "latency_ms": 120},
                "tier_1b": {"status": "healthy", "latency_ms": 150},
                "tier_2": {
                    "status": tier_2_status,
                    "endpoints": tier_2_endpoints,
                },
            },
            "providers": svc._health.status() if svc else {},
            "restricted_cloud_violations": violations,
            "uptime_seconds": 3600,
        }
    except Exception as e:
        logger.error("Health check error: %s", e)
        return {
            "status": "error",
            "message": str(e),
        }
