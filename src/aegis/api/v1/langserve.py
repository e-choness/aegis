from __future__ import annotations

import re
from typing import Any, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

from ...models import (
    WorkflowInvokeRequest,
    WorkflowInvokeResponse,
    WorkflowBatchRequest,
    WorkflowBatchResponse,
)
from ...services.team_context import TeamContext, TeamContextManager
from ...services.workflow_engine import WorkflowEngine
from ...services.langserve_adapter import LangServeAdapter

router = APIRouter(prefix="/api/v1/workflows", tags=["langserve"])


class WorkflowListResponse(BaseModel):
    """Response for listing registered workflows."""
    workflows: list[dict[str, Any]] = Field(description="List of registered workflow definitions")
    count: int = Field(description="Number of workflows")


def _team_context(
    request: Request,
    x_team_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TeamContext:
    """Extract or build TeamContext from request."""
    if not x_team_id or not x_user_id:
        raise HTTPException(400, "X-Team-ID and X-User-ID headers are required")
    if not _ID_RE.match(x_team_id):
        raise HTTPException(400, "Invalid X-Team-ID format")
    if not _ID_RE.match(x_user_id):
        raise HTTPException(400, "Invalid X-User-ID format")
    existing = getattr(request.state, "team_context", None)
    if existing is not None:
        return existing
    manager: TeamContextManager = getattr(request.app.state, "team_context_manager", None)
    if manager is None:
        raise HTTPException(503, "Team context manager not initialized")
    try:
        return manager.build_context(x_team_id, x_user_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _engine(request: Request) -> WorkflowEngine:
    """Get WorkflowEngine from app state."""
    engine = getattr(request.app.state, "workflow_engine", None)
    if engine is None:
        raise HTTPException(503, "Workflow engine not initialized")
    return engine


def _adapter(request: Request) -> LangServeAdapter:
    """Get or create LangServeAdapter from WorkflowEngine."""
    engine = _engine(request)
    adapter = getattr(request.app.state, "langserve_adapter", None)
    if adapter is None:
        adapter = LangServeAdapter(engine)
        request.app.state.langserve_adapter = adapter
    return adapter


@router.post("/{workflow_id}/invoke", response_model=WorkflowInvokeResponse)
async def invoke_workflow(
    workflow_id: str,
    body: WorkflowInvokeRequest,
    team_context: TeamContext = Depends(_team_context),
    adapter: LangServeAdapter = Depends(_adapter),
) -> WorkflowInvokeResponse:
    """
    Synchronously invoke a workflow and return results.

    This is the LangServe-compatible synchronous invoke operation.
    Results include usage metrics, execution metadata, and structured output.
    """
    # Validate workflow exists before invoking so we can return 404
    try:
        adapter.schema(workflow_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(404, str(e).strip("'\"")) from e

    try:
        return await adapter.invoke(
            team_context=team_context,
            workflow_id=workflow_id,
            input_data=body.input or {},
            config=body.config,
        )
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\"")) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Workflow invocation failed: {str(e)}") from e


@router.post("/{workflow_id}/stream")
async def stream_workflow(
    workflow_id: str,
    body: WorkflowInvokeRequest,
    team_context: TeamContext = Depends(_team_context),
    adapter: LangServeAdapter = Depends(_adapter),
):
    """
    Stream workflow execution events via Server-Sent Events (SSE).

    Events include:
    - start: Execution initiated with execution_id
    - checkpoint: State checkpoint with current step
    - complete: Successful completion with output and metadata
    - error: Failure with error message

    Connect and listen for streaming events. Each event is a JSON object.
    """
    # Validate workflow exists before opening stream so we can return 404
    try:
        adapter.schema(workflow_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(404, str(e).strip("'\"")) from e

    try:
        async def event_generator():
            try:
                async for event in adapter.stream(
                    team_context=team_context,
                    workflow_id=workflow_id,
                    input_data=body.input or {},
                    config=body.config,
                ):
                    import json
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Stream setup failed: {str(e)}") from e


@router.post("/{workflow_id}/batch", response_model=WorkflowBatchResponse)
async def batch_workflow(
    workflow_id: str,
    body: WorkflowBatchRequest,
    team_context: TeamContext = Depends(_team_context),
    adapter: LangServeAdapter = Depends(_adapter),
) -> WorkflowBatchResponse:
    """
    Execute workflow against multiple inputs with concurrency control.

    Executes each input in parallel (up to max_concurrency), preserving
    input order in results. Partial failures don't stop other executions.
    """
    try:
        results = await adapter.batch(
            team_context=team_context,
            workflow_id=workflow_id,
            inputs=body.inputs,
            config=body.config,
            max_concurrency=body.max_concurrency,
        )
        return WorkflowBatchResponse(executions=results)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\"")) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Batch execution failed: {str(e)}") from e


@router.get("/list", response_model=WorkflowListResponse)
async def list_workflows(
    request: Request,
    team_context: TeamContext = Depends(_team_context),
) -> WorkflowListResponse:
    """
    List all registered workflows available to the team.

    Returns workflow definitions with metadata (name, description, etc.)
    """
    try:
        gateway = getattr(request.app.state, "langgraph_gateway", None)
        if gateway is None:
            raise HTTPException(503, "LangGraph gateway not initialized")
        workflows = [w.to_dict() for w in gateway.get_registered_workflows()]
        return WorkflowListResponse(workflows=workflows, count=len(workflows))
    except Exception as e:
        raise HTTPException(500, f"Failed to list workflows: {str(e)}") from e


@router.get("/{workflow_id}/schema")
async def get_workflow_schema(
    workflow_id: str,
    team_context: TeamContext = Depends(_team_context),
    adapter: LangServeAdapter = Depends(_adapter),
) -> dict[str, Any]:
    """
    Retrieve workflow input/output schema and configuration metadata.

    Returns:
    - title: Workflow name/description
    - description: Workflow purpose
    - input_schema: Pydantic schema for input
    - output_schema: Pydantic schema for output
    - config_schema: Pydantic schema for config overrides
    """
    try:
        return adapter.schema(workflow_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Schema retrieval failed: {str(e)}") from e
