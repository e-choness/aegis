from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...services.team_context import TeamContext, TeamContextManager
from ...services.tool_registry import ToolRegistry

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class ToolCallRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


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


def _registry(request: Request) -> ToolRegistry:
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise HTTPException(503, "Tool registry not initialized")
    return registry


@router.get("/list")
async def list_tools(
    team_context: TeamContext = Depends(_team_context),
    registry: ToolRegistry = Depends(_registry),
):
    tools = [definition.to_dict() for definition in registry.list_tools(team_context=team_context)]
    return {"tools": tools, "count": len(tools)}


@router.get("/{tool_name}")
async def get_tool(
    tool_name: str,
    team_context: TeamContext = Depends(_team_context),
    registry: ToolRegistry = Depends(_registry),
):
    try:
        tool = registry.get_tool(tool_name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if tool.definition not in registry.list_tools(team_context=team_context):
        raise HTTPException(403, "Team is not permitted to use this tool")
    return tool.definition.to_dict()


@router.post("/{tool_name}/validate")
async def validate_tool_call(
    tool_name: str,
    body: ToolCallRequest,
    team_context: TeamContext = Depends(_team_context),
    registry: ToolRegistry = Depends(_registry),
):
    result = registry.validate_tool_call(team_context, tool_name, body.args)
    return result.to_dict()


@router.post("/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    body: ToolCallRequest,
    team_context: TeamContext = Depends(_team_context),
    registry: ToolRegistry = Depends(_registry),
):
    if not team_context.has_permission("admin"):
        raise HTTPException(403, "Direct tool execution requires admin permission")
    try:
        result = await registry.execute_tool(team_context, tool_name, body.args)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.to_dict()
