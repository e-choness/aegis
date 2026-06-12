"""Tests for Step 11: AegisMcpServer — governed routes as MCP tools.

Gate: DC uv run pytest packages/aegis-core packages/aegis-server -q -k mcp
"""

from __future__ import annotations

from mcp.shared.memory import create_connected_server_and_client_session

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.mcp import AegisMcpServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(*routes: str) -> PipelineExecutor:
    """Build an executor with fake providers for *routes*."""
    ex = PipelineExecutor()
    for route in routes:
        ex.register(route, provider=FakeProvider(complete_response=f"response from {route}"))
    return ex


# ---------------------------------------------------------------------------
# AegisMcpServer — tools list
# ---------------------------------------------------------------------------


class TestAegisMcpServerToolsList:
    async def test_routes_exposed_as_tools(self) -> None:
        """Each registered route becomes an MCP tool named route_<name>."""
        executor = _make_executor("default", "drafts")
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            tools_response = await session.list_tools()

        tool_names = {t.name for t in tools_response.tools}
        assert "route_default" in tool_names
        assert "route_drafts" in tool_names

    async def test_single_route_exposed(self) -> None:
        executor = _make_executor("default")
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            tools_response = await session.list_tools()

        assert len(tools_response.tools) == 1
        assert tools_response.tools[0].name == "route_default"

    def test_tool_names_helper(self) -> None:
        executor = _make_executor("alpha", "beta")
        srv = AegisMcpServer(executor)
        assert set(srv.tool_names()) == {"route_alpha", "route_beta"}

    def test_server_info(self) -> None:
        executor = _make_executor("default")
        srv = AegisMcpServer(executor, server_name="test-aegis")
        info = srv.server_info()
        assert info["server_name"] == "test-aegis"
        assert "default" in info["routes"]
        assert "route_default" in info["tools"]


# ---------------------------------------------------------------------------
# AegisMcpServer — call round trip
# ---------------------------------------------------------------------------


class TestAegisMcpServerCallRoundTrip:
    async def test_call_tool_returns_route_response(self) -> None:
        """Calling a route tool returns the governed pipeline's text response."""
        executor = _make_executor("default")
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            result = await session.call_tool("route_default", {"prompt": "hello"})

        assert result.isError is False
        content = result.content
        assert content, "Expected non-empty content"
        text = content[0].text  # type: ignore[union-attr]
        assert "response from default" in text

    async def test_call_tool_for_second_route(self) -> None:
        executor = _make_executor("default", "drafts")
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            result = await session.call_tool("route_drafts", {"prompt": "test"})

        assert result.isError is False
        text = result.content[0].text  # type: ignore[union-attr]
        assert "response from drafts" in text

    async def test_call_tool_prompt_passed_to_provider(self) -> None:
        """The prompt argument is forwarded as the user message."""
        from aegis_core.providers.models import CompletionRequest

        fake = FakeProvider(complete_response="echo")
        executor = PipelineExecutor()
        executor.register("default", provider=fake)
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            await session.call_tool("route_default", {"prompt": "test-content"})

        assert fake.complete_calls
        req: CompletionRequest = fake.complete_calls[0]
        assert any(m.content == "test-content" for m in req.messages)

    async def test_tool_description_includes_route_name(self) -> None:
        executor = _make_executor("my_route")
        srv = AegisMcpServer(executor)

        async with create_connected_server_and_client_session(srv.server) as session:
            tools = await session.list_tools()

        tool = next(t for t in tools.tools if t.name == "route_my_route")
        assert "my_route" in (tool.description or "")

    async def test_server_name_in_initialize(self) -> None:
        """Server name is set correctly in MCP initialization."""
        executor = _make_executor("default")
        srv = AegisMcpServer(executor, server_name="aegis-test")
        # FastMCP server name is accessible
        assert srv.server.name == "aegis-test"
