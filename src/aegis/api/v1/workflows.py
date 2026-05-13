from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...services.team_context import TeamContext, TeamContextManager
from ...services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


class WorkflowExecuteRequest(BaseModel):
    input_data: dict[str, Any] = Field(default_factory=dict)
    tools: Optional[list[str]] = None
    timeout_seconds: Optional[int] = None
    async_mode: bool = False
    queue: bool = False
    priority: int = Field(default=5, ge=1, le=10)


class WorkflowSubmitResponse(BaseModel):
    workflow_instance_id: Optional[str] = None
    queue_id: Optional[str] = None
    status: str


class WorkflowStatusResponse(BaseModel):
    workflow_instance_id: str
    team_id: str
    user_id: str
    workflow_id: str
    status: str
    current_step: str
    input_data: dict[str, Any]
    output_data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    execution_time_seconds: float
    cost_usd: float
    model_calls_count: int
    tool_calls_count: int
    conversation_id: Optional[str] = None


class ResumeWorkflowRequest(BaseModel):
    user_input: str = Field(min_length=1)


def _team_context(
    request: Request,
    x_team_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TeamContext:
    existing = getattr(request.state, "team_context", None)
    if existing is not None:
        return existing
    if not x_team_id or not x_user_id:
        raise HTTPException(400, "X-Team-ID and X-User-ID headers are required")
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
    engine = getattr(request.app.state, "workflow_engine", None)
    if engine is None:
        raise HTTPException(503, "Workflow engine not initialized")
    return engine


@router.post("/{workflow_id}/execute", response_model=WorkflowSubmitResponse, status_code=202)
async def execute_workflow(
    workflow_id: str,
    body: WorkflowExecuteRequest,
    team_context: TeamContext = Depends(_team_context),
    engine: WorkflowEngine = Depends(_engine),
):
    if body.queue:
        queue_id = await engine.queue_workflow(
            team_context=team_context,
            workflow_id=workflow_id,
            input_data=body.input_data,
            priority=body.priority,
        )
        return WorkflowSubmitResponse(queue_id=queue_id, status="queued")

    if body.async_mode:
        workflow_instance_id = await engine.submit_workflow(
            team_context=team_context,
            workflow_id=workflow_id,
            input_data=body.input_data,
            tools=body.tools,
        )
        return WorkflowSubmitResponse(workflow_instance_id=workflow_instance_id, status="running")

    result = await engine.execute_workflow(
        team_context=team_context,
        workflow_id=workflow_id,
        input_data=body.input_data,
        tools=body.tools,
    )
    return WorkflowSubmitResponse(
        workflow_instance_id=result.workflow_instance_id,
        status=result.status,
    )


@router.get("/instances/{workflow_instance_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    workflow_instance_id: str,
    team_context: TeamContext = Depends(_team_context),
    engine: WorkflowEngine = Depends(_engine),
):
    status = engine.get_workflow_status(workflow_instance_id)
    if status is None or status.team_id != team_context.team_id:
        raise HTTPException(404, "Workflow instance not found")
    return WorkflowStatusResponse(**status.to_dict())


@router.get("/instances/{workflow_instance_id}/history")
async def get_workflow_history(
    workflow_instance_id: str,
    limit: int = 50,
    offset: int = 0,
    team_context: TeamContext = Depends(_team_context),
    engine: WorkflowEngine = Depends(_engine),
):
    status = engine.get_workflow_status(workflow_instance_id)
    if status is None or status.team_id != team_context.team_id:
        raise HTTPException(404, "Workflow instance not found")
    messages = await engine.get_conversation_history(workflow_instance_id, limit=limit, offset=offset)
    return {"messages": [message.to_dict() for message in messages], "total_count": len(messages)}


@router.post("/instances/{workflow_instance_id}/resume", response_model=WorkflowSubmitResponse, status_code=202)
async def resume_workflow(
    workflow_instance_id: str,
    body: ResumeWorkflowRequest,
    team_context: TeamContext = Depends(_team_context),
    engine: WorkflowEngine = Depends(_engine),
):
    status = engine.get_workflow_status(workflow_instance_id)
    if status is None or status.team_id != team_context.team_id:
        raise HTTPException(404, "Workflow instance not found")
    result = await engine.resume_workflow(workflow_instance_id, body.user_input)
    return WorkflowSubmitResponse(workflow_instance_id=result.workflow_instance_id, status=result.status)


@router.delete("/instances/{workflow_instance_id}", status_code=204)
async def cancel_workflow(
    workflow_instance_id: str,
    team_context: TeamContext = Depends(_team_context),
    engine: WorkflowEngine = Depends(_engine),
):
    status = engine.get_workflow_status(workflow_instance_id)
    if status is None or status.team_id != team_context.team_id:
        raise HTTPException(404, "Workflow instance not found")
    await engine.cancel_workflow(workflow_instance_id)
    return None


@router.get("/list")
async def list_workflows(request: Request, team_context: TeamContext = Depends(_team_context)):
    gateway = getattr(request.app.state, "langgraph_gateway", None)
    if gateway is None:
        raise HTTPException(503, "LangGraph gateway not initialized")
    workflows = [workflow.to_dict() for workflow in gateway.get_registered_workflows()]
    return {"workflows": workflows, "count": len(workflows)}
