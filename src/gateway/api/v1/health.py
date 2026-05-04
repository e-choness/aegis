from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health(request: Request):
    svc = request.app.state.inference_service
    violations = svc._audit.count_restricted_cloud_violations()
    return {
        "status": "ok",
        "providers": svc._health.status(),
        "restricted_cloud_violations": violations,
    }
