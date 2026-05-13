"""LangServe-compatible API endpoints for Runnable chains.

Implements the LangServe HTTP API spec for:
- /runnables/{name}/invoke — synchronous invocation
- /runnables/{name}/batch — batch invocation
- /runnables/{name}/stream — streaming via Server-Sent Events
- /runnables/{name}/schema — JSON schema introspection
- /runnables — list available Runnables
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...models import DataClassification, InferenceRequest
from ...services.inference import InferenceService
from ...services.runnable_factory import RunnableFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _get_inference_service(request: Request) -> InferenceService:
    """Dependency: get InferenceService from app state."""
    svc = getattr(request.app.state, "inference_service", None)
    if svc is None:
        raise HTTPException(503, "Inference service not initialized")
    return svc


def _get_runnable_factory(request: Request) -> RunnableFactory:
    """Dependency: get RunnableFactory from app state."""
    factory = getattr(request.app.state, "runnable_factory", None)
    if factory is None:
        raise HTTPException(503, "Runnable factory not initialized")
    return factory


@router.get("/runnables")
async def list_runnables(
    factory: RunnableFactory = Depends(_get_runnable_factory),
) -> dict[str, Any]:
    """List all available Runnables with metadata.
    
    Returns:
        {
            "runnables": [
                {
                    "name": "inference",
                    "description": "...",
                    "tags": ["inference", "classification"],
                    "input_schema": {...},
                    "output_schema": {...}
                }
            ]
        }
    """
    return {"runnables": factory.list_runnables()}


@router.get("/runnables/{name}/schema")
async def get_runnable_schema(
    name: str,
    factory: RunnableFactory = Depends(_get_runnable_factory),
) -> dict[str, Any]:
    """Get input/output JSON schemas for a Runnable.
    
    Returns:
        {
            "name": "inference",
            "description": "...",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            },
            "output_schema": {
                "type": "object",
                "properties": {...}
            }
        }
    """
    schema = factory.get_schema(name)
    if schema is None:
        raise HTTPException(404, f"Runnable {name!r} not found")
    return schema


@router.post("/runnables/{name}/invoke")
async def invoke_runnable(
    name: str,
    body: dict[str, Any],
    request: Request,
    svc: InferenceService = Depends(_get_inference_service),
    factory: RunnableFactory = Depends(_get_runnable_factory),
) -> dict[str, Any]:
    """Invoke a Runnable synchronously and return the result.
    
    Request body:
        {
            "input": {
                "prompt": "...",
                "task_type": "...",
                "team_id": "...",
                "user_id": "..."
            },
            "config": {
                "metadata": {"trace_id": "..."}
            }
        }
    
    Response:
        {
            "output": "...",
            "metadata": {
                "model_alias": "sonnet",
                "provider": "anthropic",
                "cost_usd": 0.0023,
                "latency_ms": 1240
            }
        }
    """
    try:
        input_data = body.get("input", {})
        config = body.get("config", {})
        
        # Validate Runnable exists
        if factory.get_schema(name) is None:
            raise HTTPException(404, f"Runnable {name!r} not found")
        
        # Convert LangServe input format to InferenceRequest
        # For "inference" runnable, input_data contains prompt, task_type, etc.
        if name == "inference":
            req = InferenceRequest(
                prompt=input_data.get("prompt", ""),
                task_type=input_data.get("task_type", "general"),
                team_id=input_data.get("team_id", ""),
                user_id=input_data.get("user_id", ""),
                complexity=input_data.get("complexity", "medium"),
                trace_id=config.get("metadata", {}).get("trace_id"),
            )
            
            if not req.team_id or not req.user_id:
                raise HTTPException(400, "team_id and user_id are required")
            
            # Enqueue job and poll until completion (synchronous)
            job_id = svc.enqueue(req)
            result = svc.get_job(job_id)
            
            # Wait for result (polling)
            max_polls = 300  # 5 minutes at 1s interval
            for _ in range(max_polls):
                result = svc.get_job(job_id)
                if result is None:
                    raise HTTPException(404, f"Job {job_id!r} not found")
                if result.status in ("completed", "failed"):
                    break
                import asyncio
                await asyncio.sleep(1)
            
            return {
                "output": result.content if result.status == "completed" else None,
                "metadata": {
                    "job_id": result.job_id,
                    "status": result.status,
                    "model_alias": result.model_alias,
                    "provider": result.provider,
                    "tier": result.tier,
                    "cost_usd": result.cost_usd,
                    "data_class": result.data_classification,
                    "error": result.error if result.status == "failed" else None,
                }
            }
        else:
            raise HTTPException(
                501, f"Runnable {name!r} invoke not yet implemented"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error invoking Runnable {name}: {e}")
        raise HTTPException(500, f"Internal error: {str(e)}")


@router.post("/runnables/{name}/batch")
async def batch_invoke_runnable(
    name: str,
    body: dict[str, Any],
    request: Request,
    svc: InferenceService = Depends(_get_inference_service),
    factory: RunnableFactory = Depends(_get_runnable_factory),
) -> dict[str, Any]:
    """Invoke a Runnable with multiple inputs and return all results.
    
    Request body:
        {
            "inputs": [
                {"prompt": "...", "task_type": "...", "team_id": "...", "user_id": "..."},
                {"prompt": "...", "task_type": "...", "team_id": "...", "user_id": "..."}
            ],
            "config": {
                "metadata": {"trace_id": "..."}
            }
        }
    
    Response:
        {
            "outputs": [
                {"output": "...", "metadata": {...}},
                {"output": "...", "metadata": {...}}
            ]
        }
    """
    try:
        inputs = body.get("inputs", [])
        config = body.get("config", {})
        
        if factory.get_schema(name) is None:
            raise HTTPException(404, f"Runnable {name!r} not found")
        
        if not inputs:
            raise HTTPException(400, "inputs field is required and must be non-empty")
        
        if name == "inference":
            outputs = []
            for input_data in inputs:
                req = InferenceRequest(
                    prompt=input_data.get("prompt", ""),
                    task_type=input_data.get("task_type", "general"),
                    team_id=input_data.get("team_id", ""),
                    user_id=input_data.get("user_id", ""),
                    complexity=input_data.get("complexity", "medium"),
                    trace_id=config.get("metadata", {}).get("trace_id"),
                )
                
                if not req.team_id or not req.user_id:
                    raise HTTPException(400, "team_id and user_id are required for each input")
                
                job_id = svc.enqueue(req)
                result = svc.get_job(job_id)
                
                # Poll until completion
                max_polls = 300
                for _ in range(max_polls):
                    result = svc.get_job(job_id)
                    if result is None:
                        raise HTTPException(404, f"Job {job_id!r} not found")
                    if result.status in ("completed", "failed"):
                        break
                    import asyncio
                    await asyncio.sleep(1)
                
                outputs.append({
                    "output": result.content if result.status == "completed" else None,
                    "metadata": {
                        "job_id": result.job_id,
                        "status": result.status,
                        "model_alias": result.model_alias,
                        "provider": result.provider,
                        "tier": result.tier,
                        "cost_usd": result.cost_usd,
                        "error": result.error if result.status == "failed" else None,
                    }
                })
            
            return {"outputs": outputs}
        else:
            raise HTTPException(
                501, f"Runnable {name!r} batch not yet implemented"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error batch invoking Runnable {name}: {e}")
        raise HTTPException(500, f"Internal error: {str(e)}")


@router.get("/runnables/{name}/stream")
async def stream_runnable(
    name: str,
    input_json: Optional[str] = None,
    request: Request = None,
    svc: InferenceService = Depends(_get_inference_service),
    factory: RunnableFactory = Depends(_get_runnable_factory),
) -> StreamingResponse:
    """Stream a Runnable's output via Server-Sent Events.
    
    Query params:
        input_json: JSON-encoded input data
    
    Response: Server-Sent Events stream
        event: token
        data: {"token": "The", "metadata": {...}}
        
        event: token
        data: {"token": " code", "metadata": {...}}
        
        event: done
        data: {"output": "...", "metadata": {...}}
    """
    try:
        if factory.get_schema(name) is None:
            raise HTTPException(404, f"Runnable {name!r} not found")
        
        if not input_json:
            raise HTTPException(400, "input_json query parameter is required")
        
        try:
            input_data = json.loads(input_json)
        except json.JSONDecodeError:
            raise HTTPException(400, "input_json must be valid JSON")
        
        if name == "inference":
            async def event_generator():
                try:
                    req = InferenceRequest(
                        prompt=input_data.get("prompt", ""),
                        task_type=input_data.get("task_type", "general"),
                        team_id=input_data.get("team_id", ""),
                        user_id=input_data.get("user_id", ""),
                        complexity=input_data.get("complexity", "medium"),
                        trace_id=input_data.get("trace_id"),
                    )
                    
                    if not req.team_id or not req.user_id:
                        yield f'event: error\ndata: {{"error": "team_id and user_id are required"}}\n\n'
                        return
                    
                    job_id = svc.enqueue(req)
                    
                    # Poll and stream tokens
                    max_polls = 300
                    buffer = ""
                    last_pos = 0
                    
                    for _ in range(max_polls):
                        result = svc.get_job(job_id)
                        if result is None:
                            yield f'event: error\ndata: {{"error": "Job not found"}}\n\n'
                            return
                        
                        if result.content:
                            buffer = result.content
                            # Stream new tokens (simple char-by-char for now)
                            while last_pos < len(buffer):
                                token = buffer[last_pos]
                                metadata = {
                                    "job_id": job_id,
                                    "status": result.status,
                                    "model_alias": result.model_alias,
                                    "provider": result.provider,
                                }
                                event_data = {
                                    "token": token,
                                    "metadata": metadata
                                }
                                yield f"event: token\ndata: {json.dumps(event_data)}\n\n"
                                last_pos += 1
                        
                        if result.status in ("completed", "failed"):
                            # Send final event
                            final_data = {
                                "output": result.content if result.status == "completed" else None,
                                "metadata": {
                                    "job_id": job_id,
                                    "status": result.status,
                                    "model_alias": result.model_alias,
                                    "provider": result.provider,
                                    "tier": result.tier,
                                    "cost_usd": result.cost_usd,
                                    "error": result.error if result.status == "failed" else None,
                                }
                            }
                            yield f"event: done\ndata: {json.dumps(final_data)}\n\n"
                            return
                        
                        import asyncio
                        await asyncio.sleep(0.5)
                    
                    # Timeout
                    yield f'event: error\ndata: {{"error": "Request timeout"}}\n\n'
                
                except Exception as e:
                    logger.exception(f"Error streaming Runnable {name}: {e}")
                    yield f'event: error\ndata: {{"error": "{str(e)}"}}\n\n'
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
            )
        else:
            raise HTTPException(
                501, f"Runnable {name!r} streaming not yet implemented"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error setting up stream for Runnable {name}: {e}")
        raise HTTPException(500, f"Internal error: {str(e)}")
