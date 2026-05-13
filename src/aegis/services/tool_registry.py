from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional, Protocol

from ..telemetry import tool_call_count, tool_call_duration_seconds, tool_validation_failures
from .team_context import TeamContext, TeamContextManager


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    min_tier: int = 1
    data_classification: str = "INTERNAL"
    cost_per_call_usd: float = 0.0
    requires_approval: bool = False
    timeout_seconds: int = 10
    safety_validators: list[str] = field(default_factory=list)
    team_whitelist: Optional[list[str]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolValidationResult:
    valid: bool
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    requires_approval: bool = False
    sandbox_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    output: dict[str, Any]
    cost_usd: float
    latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentTool(Protocol):
    definition: ToolDefinition

    def validate(self, args: dict[str, Any]) -> list[str]:
        ...

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        ...


class FunctionTool:
    """Adapter for lightweight async/sync tool callables."""

    def __init__(
        self,
        definition: ToolDefinition,
        func: Callable[[TeamContext, dict[str, Any]], Any],
        validator: Optional[Callable[[dict[str, Any]], list[str]]] = None,
    ) -> None:
        self.definition = definition
        self._func = func
        self._validator = validator

    def validate(self, args: dict[str, Any]) -> list[str]:
        if self._validator is None:
            return []
        return self._validator(args)

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        result = self._func(team_context, args)
        if inspect.isawaitable(result):
            result = await result
        return dict(result)


class ToolRegistry:
    """Central registry, validation, and execution boundary for workflow tools."""

    def __init__(self, team_context_manager: Optional[TeamContextManager] = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._team_context_manager = team_context_manager or TeamContextManager()

    def register_tool(self, tool: AgentTool) -> None:
        self._tools[tool.definition.name] = tool

    def get_tool(self, tool_name: str) -> AgentTool:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Tool {tool_name!r} is not registered") from exc

    def list_tools(
        self,
        team_context: Optional[TeamContext] = None,
        filter_by_tier: Optional[int] = None,
    ) -> list[ToolDefinition]:
        definitions: list[ToolDefinition] = []
        for tool in self._tools.values():
            definition = tool.definition
            if filter_by_tier is not None and definition.min_tier > filter_by_tier:
                continue
            if team_context is not None and not self._team_can_use_tool(team_context, definition):
                continue
            definitions.append(definition)
        return sorted(definitions, key=lambda item: item.name)

    def validate_tool_call(
        self,
        team_context: TeamContext,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolValidationResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            tool_validation_failures.labels(tool_name=tool_name, failure_reason="unknown_tool").inc()
            return ToolValidationResult(valid=False, error=f"Unknown tool: {tool_name}")

        definition = tool.definition
        if not self._team_can_use_tool(team_context, definition):
            tool_validation_failures.labels(tool_name=tool_name, failure_reason="permission").inc()
            return ToolValidationResult(
                valid=False,
                error=f"Team {team_context.team_id!r} is not permitted to use {tool_name!r}",
                estimated_cost=definition.cost_per_call_usd,
                requires_approval=definition.requires_approval,
                sandbox_mode="sandbox" in definition.safety_validators,
            )

        schema_errors = _validate_json_schema(definition.input_schema, args)
        validation_args = {**args, "_team_id": team_context.team_id}
        custom_errors = tool.validate(validation_args)
        errors = schema_errors + custom_errors
        if errors:
            tool_validation_failures.labels(tool_name=tool_name, failure_reason="schema").inc()
            return ToolValidationResult(
                valid=False,
                error="; ".join(errors),
                estimated_cost=definition.cost_per_call_usd,
                requires_approval=definition.requires_approval,
                sandbox_mode="sandbox" in definition.safety_validators,
            )

        if team_context.budget_remaining_usd < definition.cost_per_call_usd:
            tool_validation_failures.labels(tool_name=tool_name, failure_reason="budget").inc()
            return ToolValidationResult(
                valid=False,
                error="Insufficient team budget for tool call",
                estimated_cost=definition.cost_per_call_usd,
                requires_approval=definition.requires_approval,
                sandbox_mode="sandbox" in definition.safety_validators,
            )

        return ToolValidationResult(
            valid=True,
            estimated_cost=definition.cost_per_call_usd,
            requires_approval=definition.requires_approval,
            sandbox_mode="sandbox" in definition.safety_validators,
        )

    async def execute_tool(
        self,
        team_context: TeamContext,
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolResult:
        tool = self.get_tool(tool_name)
        validation = self.validate_tool_call(team_context, tool_name, args)
        if not validation.valid:
            tool_call_count.labels(tool_name=tool_name, team_id=team_context.team_id, success="false").inc()
            raise ValueError(validation.error or "Tool validation failed")

        start = time.monotonic()
        try:
            output = await asyncio.wait_for(
                tool.execute(team_context, args),
                timeout=max(1, tool.definition.timeout_seconds),
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            tool_call_duration_seconds.labels(tool_name=tool_name).observe(latency_ms / 1000)
            tool_call_count.labels(tool_name=tool_name, team_id=team_context.team_id, success="true").inc()
            return ToolResult(
                tool_name=tool_name,
                output=output,
                cost_usd=tool.definition.cost_per_call_usd,
                latency_ms=latency_ms,
            )
        except Exception:
            latency_ms = int((time.monotonic() - start) * 1000)
            tool_call_duration_seconds.labels(tool_name=tool_name).observe(latency_ms / 1000)
            tool_call_count.labels(tool_name=tool_name, team_id=team_context.team_id, success="false").inc()
            raise

    def _team_can_use_tool(self, team_context: TeamContext, definition: ToolDefinition) -> bool:
        if definition.team_whitelist and team_context.team_id not in definition.team_whitelist:
            return False
        return self._team_context_manager.validate_tool_access(team_context, definition.name)


def _validate_json_schema(schema: dict[str, Any], args: dict[str, Any]) -> list[str]:
    """Small JSON-schema subset validator for tool boundaries."""

    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(args, dict):
        return ["args must be an object"]

    for required in schema.get("required", []):
        if required not in args:
            errors.append(f"{required} is required")

    properties = schema.get("properties", {})
    for key, value in args.items():
        prop = properties.get(key)
        if prop is None:
            continue
        expected = prop.get("type")
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{key} must be a string")
        elif expected == "integer" and not isinstance(value, int):
            errors.append(f"{key} must be an integer")
        elif expected == "number" and not isinstance(value, (int, float)):
            errors.append(f"{key} must be a number")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} must be a boolean")

        if isinstance(value, str):
            min_length = prop.get("minLength")
            max_length = prop.get("maxLength")
            if min_length is not None and len(value) < int(min_length):
                errors.append(f"{key} must be at least {min_length} characters")
            if max_length is not None and len(value) > int(max_length):
                errors.append(f"{key} must be at most {max_length} characters")

        if isinstance(value, (int, float)):
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"{key} must be >= {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"{key} must be <= {maximum}")

        if "enum" in prop and value not in prop["enum"]:
            errors.append(f"{key} must be one of {prop['enum']}")

    return errors
