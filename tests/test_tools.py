from __future__ import annotations

import pytest

from src.aegis.services.team_context import TeamContextManager
from src.aegis.services.tool_registry import ToolRegistry
from src.aegis.tools import register_builtin_tools
from src.aegis.tools.code_execution import validate_python_code
from src.aegis.tools.data_retrieval import validate_read_only_sql
from src.aegis.tools.web_search import is_safe_public_url


@pytest.fixture
def team_manager():
    manager = TeamContextManager()
    manager.register_team(
        "team-code",
        members={"alice"},
        permissions={"execute_workflow", "use_web_tools", "use_data_tools", "use_code_execution"},
        budget_remaining_usd=10.0,
    )
    return manager


@pytest.fixture
def registry(team_manager):
    registry = ToolRegistry(team_context_manager=team_manager)
    register_builtin_tools(registry)
    return registry


def test_list_tools_filters_by_team_permissions(registry, team_manager):
    context = team_manager.build_context("team-default", "bob")
    tool_names = {tool.name for tool in registry.list_tools(context)}
    assert {"web_search", "database_query", "vector_search"}.issubset(tool_names)
    assert "code_execute" not in tool_names


def test_validate_tool_call_rejects_bad_schema(registry, team_manager):
    context = team_manager.build_context("team-default", "bob")
    result = registry.validate_tool_call(context, "web_search", {"query": "rag", "max_results": 99})
    assert not result.valid
    assert "max_results" in result.error


def test_web_search_url_validator_blocks_private_targets():
    assert is_safe_public_url("https://example.com/page")
    assert not is_safe_public_url("http://localhost:8000")
    assert not is_safe_public_url("http://127.0.0.1:8000")
    assert not is_safe_public_url("http://10.0.0.4/status")


def test_code_execution_ast_blocks_dangerous_patterns():
    assert validate_python_code("print(1 + 1)") == []
    errors = validate_python_code("import os\nos.system('whoami')")
    assert any("imports are blocked" in error for error in errors)
    assert any("os.system" in error for error in errors)


@pytest.mark.asyncio
async def test_code_execute_runs_safe_python_in_sandbox(registry, team_manager):
    context = team_manager.build_context("team-code", "alice")
    result = await registry.execute_tool(
        context,
        "code_execute",
        {"language": "python", "code": "print(21 * 2)", "timeout_seconds": 5},
    )
    assert result.output["exit_code"] == 0
    assert result.output["stdout"].strip() == "42"


def test_database_query_validation_is_read_only_and_team_scoped():
    assert validate_read_only_sql("SELECT * FROM rows", "team-a") == []
    assert validate_read_only_sql("DELETE FROM rows", "team-a") == ["only SELECT queries are allowed"]
    errors = validate_read_only_sql("SELECT * FROM rows WHERE team_id = 'team-b'", "team-a")
    assert errors == ["query attempts to access a different team_id"]


def test_tool_registry_enforces_team_scope_for_database_query(registry, team_manager):
    context = team_manager.build_context("team-code", "alice")
    result = registry.validate_tool_call(
        context,
        "database_query",
        {"query": "SELECT * FROM rows WHERE team_id = 'other-team'"},
    )
    assert not result.valid
    assert "different team_id" in result.error


def test_tool_registry_reports_unknown_tool(registry, team_manager):
    context = team_manager.build_context("team-default", "bob")
    result = registry.validate_tool_call(context, "missing_tool", {})
    assert not result.valid
    assert result.error == "Unknown tool: missing_tool"
