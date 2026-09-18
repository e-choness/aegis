"""GET /v1/health — liveness probe + config digest (OSFI E-23 Appendix 1)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/v1/health", include_in_schema=True)
async def health(request: Request) -> JSONResponse:
    """Liveness probe. Returns the running config digest."""
    return JSONResponse(
        {
            "status": "ok",
            "config_digest": getattr(request.app.state, "config_digest", None),
            "config_path": getattr(request.app.state, "config_path", None),
        }
    )
