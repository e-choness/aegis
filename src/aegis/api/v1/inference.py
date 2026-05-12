from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from ...models import InferenceRequest, InferenceResponse, JobResult
from ...services.inference import InferenceService

router = APIRouter(prefix="/api/v1")


def _svc(request: Request) -> InferenceService:
    svc = getattr(request.app.state, "inference_service", None)
    if svc is None:
        raise HTTPException(503, "Inference service not initialized")
    return svc


@router.post("/inference", response_model=InferenceResponse, status_code=202)
async def submit_inference(body: InferenceRequest, svc: InferenceService = Depends(_svc)):
    if not body.team_id or not body.user_id:
        raise HTTPException(400, "team_id and user_id are required")
    job_id = svc.enqueue(body)
    return InferenceResponse(job_id=job_id, trace_id=body.trace_id)


@router.get("/jobs/{job_id}", response_model=JobResult)
async def get_job(job_id: str, svc: InferenceService = Depends(_svc)):
    result = svc.get_job(job_id)
    if result is None:
        raise HTTPException(404, f"Job {job_id!r} not found")
    return result
