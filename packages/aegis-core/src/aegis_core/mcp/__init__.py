"""Aegis MCP support — governed tool-calling client and server.

Public API:

- :class:`McpExecuteNode` — execute-stage node with MCP tool-calling loop
- :class:`ExfiltrationGuard` — tool-call guard (blocks masked PII in args)
- :class:`ToolResultInjectionGuard` — tool-result guard (injection scan)
- :class:`ToolCallGuard` — protocol for tool-call guards
- :class:`ToolResultGuard` — protocol for tool-result guards
- :class:`ToolPolicy` — per-tool policy dataclass
- :class:`McpPolicyConfig` — collection of per-tool policies
"""

from aegis_core.mcp.execute_node import McpExecuteNode
from aegis_core.mcp.guards import ExfiltrationGuard, ToolResultInjectionGuard
from aegis_core.mcp.protocol import ToolCallGuard, ToolResultGuard
from aegis_core.mcp.tool_policy import McpPolicyConfig, ToolPolicy

__all__ = [
    "ExfiltrationGuard",
    "McpExecuteNode",
    "McpPolicyConfig",
    "ToolCallGuard",
    "ToolPolicy",
    "ToolResultGuard",
    "ToolResultInjectionGuard",
]
