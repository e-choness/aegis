from __future__ import annotations
import logging
from fastapi import APIRouter, Query, Request, HTTPException

logger = logging.getLogger("aegis.api.admin")

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/refresh-models")
async def refresh_models(request: Request):
    """
    Query all configured Tier 2 endpoints for latest model list.
    Update model cache. No authentication required (internal only).
    """
    logger.info("Admin endpoint: refresh-models requested")

    try:
        external_llm = getattr(request.app.state, "external_llm_provider", None)
        if not external_llm:
            raise HTTPException(503, "Tier 2 not available")

        models = await external_llm.discover_models()
        return {
            "status": "refreshed",
            "count": len(models),
            "message": f"Model cache refreshed with {len(models)} models",
        }
    except Exception as e:
        logger.error("Refresh models failed: %s", e)
        return {
            "status": "error",
            "message": str(e),
        }


@router.post("/reset-circuit-breaker")
async def reset_circuit_breaker(request: Request, endpoint: str = Query(..., description="Endpoint URL")):
    """
    Clear circuit breaker failures for a specific endpoint.
    Query param: endpoint (e.g., http://lm-studio-1.local:8000)
    """
    logger.info("Admin endpoint: reset-circuit-breaker for %s", endpoint)

    try:
        failover = getattr(request.app.state, "tier2_failover", None)
        if not failover:
            raise HTTPException(503, "Tier 2 not available")

        success = failover.reset_circuit_breaker(endpoint)
        if not success:
            raise ValueError(f"Endpoint {endpoint} not found in failover configuration")

        return {
            "status": "reset",
            "endpoint": endpoint,
            "message": "Circuit breaker reset",
        }
    except Exception as e:
        logger.error("Reset circuit breaker failed: %s", e)
        return {
            "status": "error",
            "endpoint": endpoint,
            "message": str(e),
        }


@router.get("/cache-status")
async def cache_status(request: Request):
    """
    Return cache entries with staleness.
    Shows model discovery status and TTL info.
    """
    logger.info("Admin endpoint: cache-status requested")

    try:
        cache = getattr(request.app.state, "model_cache", None)
        failover = getattr(request.app.state, "tier2_failover", None)

        if not cache or not failover:
            raise HTTPException(503, "Tier 2 not available")

        cached = cache.get("tier_2")
        staleness = cache.get_staleness_seconds("tier_2")

        return {
            "tier_2": {
                "model_count": len(cached.models) if cached else 0,
                "staleness_seconds": staleness,
                "is_stale": cache.is_stale("tier_2"),
                "cache_enabled": True,
                "ttl_seconds": cache._ttl_seconds,
                "failover_status": failover.get_status(),
            }
        }
    except Exception as e:
        logger.error("Cache status failed: %s", e)
        return {
            "status": "error",
            "message": str(e),
        }
