from __future__ import annotations

import html
import ipaddress
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..services.team_context import TeamContext
from ..services.tool_registry import ToolDefinition


def is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    host = parsed.hostname.lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


@dataclass
class WebSearchTool:
    """
    Safe web-search boundary.

    The default implementation is deterministic and does not call the network; a
    production search adapter can be injected behind this same tool contract.
    """

    definition: ToolDefinition = field(default_factory=lambda: ToolDefinition(
        name="web_search",
        description="Search public web results for a query",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 5},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array"},
            },
        },
        min_tier=1,
        data_classification="PUBLIC",
        cost_per_call_usd=0.01,
        timeout_seconds=10,
        safety_validators=["url_validator", "result_sanitizer"],
    ))

    def validate(self, args: dict[str, Any]) -> list[str]:
        query = str(args.get("query", "")).strip()
        if not query:
            return ["query cannot be empty"]
        return []

    async def execute(self, team_context: TeamContext, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"]).strip()
        max_results = min(int(args.get("max_results", 3)), 5)
        safe_query = html.escape(query, quote=False)
        results = [
            {
                "title": f"Aegis search result {index + 1}",
                "url": f"https://example.com/search/{index + 1}",
                "snippet": f"Sanitized result for {safe_query}",
            }
            for index in range(max_results)
        ]
        return {"results": [result for result in results if is_safe_public_url(result["url"])]}
