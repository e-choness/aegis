"""Per-tool policy configuration (PROJECT_SPEC D13)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolPolicy:
    """Policy applied to a single named MCP tool.

    Attributes:
        name: Tool name as declared in the MCP server.
        require_approval: When ``True``, the run is paused for human review
            before the tool is invoked (reuses step-09 HITL machinery).
    """

    name: str
    require_approval: bool = False


@dataclass
class McpPolicyConfig:
    """Collection of per-tool policies for an MCP execute node.

    Attributes:
        tools: Map of tool name → :class:`ToolPolicy`.
    """

    tools: dict[str, ToolPolicy] = field(default_factory=dict)

    def for_tool(self, name: str) -> ToolPolicy:
        """Return the policy for *name*, defaulting to a permissive policy."""
        return self.tools.get(name, ToolPolicy(name=name))
