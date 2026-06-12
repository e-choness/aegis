"""AegisMcpServer — exposes Aegis-governed routes as MCP tools.

Instantiate with a :class:`~aegis_core.pipeline.executor.PipelineExecutor`
and each registered route becomes a callable MCP tool whose I/O passes
through the full governance pipeline (auth, ingress guards, egress guards,
audit events).

Usage::

    executor = PipelineExecutor(...)
    executor.register("default", provider=provider)

    srv = AegisMcpServer(executor)

    # For in-process testing:
    from mcp.shared.memory import create_connected_server_and_client_session
    async with create_connected_server_and_client_session(srv.server) as session:
        tools = await session.list_tools()
        result = await session.call_tool("route_default", {"prompt": "hello"})

    # For production (SSE / stdio / streamable-HTTP): use srv.server.run_*_async()
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message


class AegisMcpServer:
    """Wraps a :class:`PipelineExecutor` and exposes each route as an MCP tool.

    Tool names follow the pattern ``route_<route_name>`` to avoid collisions
    with other tool namespaces.

    Args:
        executor: Configured executor with at least one registered route.
        server_name: Name reported in MCP ``initialize`` responses.
    """

    def __init__(
        self,
        executor: PipelineExecutor,
        server_name: str = "aegis",
    ) -> None:
        self._executor = executor
        self._mcp = FastMCP(server_name)
        self._register_routes()

    def _register_routes(self) -> None:
        for route in self._executor.routes():
            self._add_route_tool(route)

    def _add_route_tool(self, route: str) -> None:
        """Register *route* as an MCP tool named ``route_<route>``."""
        executor = self._executor

        async def _run_route(prompt: str) -> str:
            """Run an Aegis governed route and return the text response."""
            state = RunState(
                run_id=str(uuid.uuid4()),
                route=route,
                messages=[Message(role="user", content=prompt)],
            )
            result = await executor.run(route, state)
            return result.response or ""

        _run_route.__name__ = f"route_{route}"
        _run_route.__doc__ = f"Run the '{route}' Aegis route with the given prompt."
        self._mcp.add_tool(
            _run_route,
            name=f"route_{route}",
            description=f"Run the '{route}' Aegis route with the given prompt.",
        )

    @property
    def server(self) -> FastMCP:
        """The underlying :class:`~mcp.server.fastmcp.FastMCP` instance.

        Pass to :func:`~mcp.shared.memory.create_connected_server_and_client_session`
        for in-process testing, or call ``run_sse_async()`` / ``run_stdio_async()``
        for production deployment.
        """
        return self._mcp

    def tool_names(self) -> list[str]:
        """Return the MCP tool names registered for all routes."""
        return [f"route_{r}" for r in self._executor.routes()]

    def add_route(self, route: str) -> None:
        """Register a new *route* as an MCP tool (hot-reload support)."""
        self._add_route_tool(route)

    def routes(self) -> list[str]:
        """Return all Aegis route names currently exposed as tools."""
        return self._executor.routes()

    def server_info(self) -> dict[str, Any]:
        """Return a summary dict for introspection and health checks."""
        return {
            "server_name": self._mcp.name,
            "routes": self.routes(),
            "tools": self.tool_names(),
        }
