from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..services.team_context import TeamContext
from ..services.tool_registry import ToolDefinition

_DANGEROUS_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|copy|create|replace)\b",
    re.IGNORECASE,
)
_TEAM_FILTER = re.compile(r"team_id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)


def validate_read_only_sql(query: str, team_id: str) -> list[str]:
    cleaned = query.strip()
    if not cleaned.lower().startswith("select"):
        return ["only SELECT queries are allowed"]
    if ";" in cleaned[:-1] or _DANGEROUS_SQL.search(cleaned):
        return ["query contains a blocked SQL operation"]
    match = _TEAM_FILTER.search(cleaned)
    if match and match.group(1) != team_id:
        return ["query attempts to access a different team_id"]
    return []


@dataclass
class DatabaseQueryTool:
    data_by_team: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    definition: ToolDefinition = field(default_factory=lambda: ToolDefinition(
        name="database_query",
        description="Run a read-only query against the calling team's data",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 6, "maxLength": 5000},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        min_tier=1,
        data_classification="INTERNAL",
        cost_per_call_usd=0.001,
        timeout_seconds=5,
        safety_validators=["sql_read_only", "team_scope"],
    ))

    def validate(self, args: dict[str, Any]) -> list[str]:
        team_id = str(args.get("_team_id", ""))
        if not team_id:
            return []
        return validate_read_only_sql(str(args.get("query", "")), team_id)

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        rows = self.data_by_team.get(team_context.team_id, [])
        return {"rows": rows, "count": len(rows)}


@dataclass
class VectorSearchTool:
    documents_by_team: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    definition: ToolDefinition = field(default_factory=lambda: ToolDefinition(
        name="vector_search",
        description="Search the calling team's vector corpus",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 1000},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
            },
        },
        min_tier=1,
        data_classification="INTERNAL",
        cost_per_call_usd=0.005,
        timeout_seconds=5,
        safety_validators=["team_scope"],
    ))

    def validate(self, args: dict[str, Any]) -> list[str]:
        return []

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        top_k = min(int(args.get("top_k", 5)), 10)
        documents = self.documents_by_team.get(team_context.team_id, [])
        results = [
            {
                "document_id": item.get("document_id", f"doc-{index + 1}"),
                "score": float(item.get("score", 1.0 - index * 0.05)),
                "text": str(item.get("text", "")),
            }
            for index, item in enumerate(documents[:top_k])
        ]
        return {"results": results}
