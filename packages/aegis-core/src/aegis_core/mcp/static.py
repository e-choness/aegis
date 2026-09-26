"""StaticToolSession — tools declared in ``aegis.yaml`` with canned results.

The governed tool loop (:class:`~aegis_core.mcp.McpExecuteNode`) talks to an
MCP ``ClientSession``. This stand-in serves tools whose result is fixed text,
so tool policies and guards can be configured, tested and demonstrated
without running a tool server — the tool equivalent of the ``fake`` provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass(frozen=True)
class StaticTool:
    """One tool: what the model is told about it and what calling it returns."""

    name: str
    description: str = ""
    result: str = ""
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


class StaticToolSession:
    """Implements the two ``ClientSession`` calls the tool loop uses."""

    def __init__(self, tools: list[StaticTool]) -> None:
        self._tools = {t.name: t for t in tools}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name=t.name, description=t.description, inputSchema=dict(t.parameters)
                )
                for t in self._tools.values()
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> SimpleNamespace:
        self.calls.append((name, arguments))
        tool = self._tools.get(name)
        text = tool.result if tool is not None else f"error: unknown tool {name!r}"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
