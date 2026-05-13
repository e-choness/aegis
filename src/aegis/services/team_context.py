from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


DEFAULT_TEAM_PERMISSIONS = {
    "execute_workflow",
    "use_web_tools",
    "use_data_tools",
}


@dataclass(frozen=True)
class TeamContext:
    """Request-scoped tenant identity and limits for Phase 2 workflows."""

    team_id: str
    user_id: str
    permissions: frozenset[str] = field(default_factory=lambda: frozenset(DEFAULT_TEAM_PERMISSIONS))
    budget_remaining_usd: float = float("inf")
    budget_reset_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30)
    )

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions or "admin" in self.permissions


@dataclass
class TeamRecord:
    team_id: str
    members: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=lambda: set(DEFAULT_TEAM_PERMISSIONS))
    budget_remaining_usd: float = float("inf")
    budget_reset_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30)
    )


class TeamContextManager:
    """
    In-memory team context store.

    The production path can back this with PostgreSQL without changing callers; the
    public API is intentionally small and team-scoped.
    """

    def __init__(self) -> None:
        self._teams: dict[str, TeamRecord] = {}

    def register_team(
        self,
        team_id: str,
        members: Optional[set[str]] = None,
        permissions: Optional[set[str]] = None,
        budget_remaining_usd: float = float("inf"),
    ) -> None:
        self._teams[team_id] = TeamRecord(
            team_id=team_id,
            members=members or set(),
            permissions=permissions or set(DEFAULT_TEAM_PERMISSIONS),
            budget_remaining_usd=budget_remaining_usd,
        )

    def build_context(self, team_id: str, user_id: str) -> TeamContext:
        if not team_id or not user_id:
            raise ValueError("team_id and user_id are required")

        record = self._teams.get(team_id)
        if record is None:
            return TeamContext(team_id=team_id, user_id=user_id)

        if record.members and user_id not in record.members:
            raise PermissionError(f"user {user_id!r} is not a member of team {team_id!r}")

        return TeamContext(
            team_id=team_id,
            user_id=user_id,
            permissions=frozenset(record.permissions),
            budget_remaining_usd=record.budget_remaining_usd,
            budget_reset_at=record.budget_reset_at,
        )

    def validate_team_access(self, team_id: str, user_id: str) -> bool:
        try:
            self.build_context(team_id, user_id)
            return True
        except (PermissionError, ValueError):
            return False

    def validate_tool_access(self, context: TeamContext, tool_name: str) -> bool:
        aliases = {
            "web_search": "use_web_tools",
            "code_execute": "use_code_execution",
            "database_query": "use_data_tools",
            "vector_search": "use_data_tools",
        }
        permission = aliases.get(tool_name, f"use_{tool_name}")
        return context.has_permission(permission)

    def validate_budget(self, context: TeamContext, cost_estimate_usd: float) -> bool:
        return context.budget_remaining_usd >= cost_estimate_usd

    def debit_budget(self, team_id: str, cost_usd: float) -> None:
        record = self._teams.get(team_id)
        if record is not None and record.budget_remaining_usd != float("inf"):
            record.budget_remaining_usd = max(0.0, record.budget_remaining_usd - cost_usd)


class TeamContextMiddleware(BaseHTTPMiddleware):
    """
    Best-effort context injector.

    Existing Phase 1 endpoints keep their request bodies and remain unaffected; Phase
    2 endpoints use explicit dependencies to require headers.
    """

    def __init__(self, app, manager: TeamContextManager):
        super().__init__(app)
        self._manager = manager

    async def dispatch(self, request: Request, call_next) -> Response:
        team_id = request.headers.get("x-team-id")
        user_id = request.headers.get("x-user-id")
        if team_id and user_id:
            try:
                request.state.team_context = self._manager.build_context(team_id, user_id)
            except (PermissionError, ValueError):
                request.state.team_context = None
        return await call_next(request)
