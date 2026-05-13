from __future__ import annotations

from ..services.tool_registry import ToolRegistry
from .code_execution import CodeExecutionTool
from .data_retrieval import DatabaseQueryTool, VectorSearchTool
from .web_search import WebSearchTool


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register_tool(WebSearchTool())
    registry.register_tool(CodeExecutionTool())
    registry.register_tool(DatabaseQueryTool())
    registry.register_tool(VectorSearchTool())


__all__ = [
    "CodeExecutionTool",
    "DatabaseQueryTool",
    "VectorSearchTool",
    "WebSearchTool",
    "register_builtin_tools",
]
