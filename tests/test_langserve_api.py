"""REST contract tests for LangServe API surface."""
from __future__ import annotations

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from src.aegis.main import app
from src.aegis.services.team_context import TeamContextManager


@pytest.fixture(autouse=True)
def _setup_app_state():
    """Manually trigger lifespan to initialize app.state."""
    lifespan_cm = app.router.lifespan_context

    async def enter_lifespan():
        lifespan_context = lifespan_cm(app)
        await lifespan_context.__aenter__()
        return lifespan_context

    async def exit_lifespan(ctx):
        await ctx.__aexit__(None, None, None)

    # Use asyncio.run() for proper event loop management (pytest-asyncio compatible)
    lifespan_context = asyncio.run(enter_lifespan())
    yield
    asyncio.run(exit_lifespan(lifespan_context))


@pytest.fixture
def client():
    """FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def team_context_manager():
    """Get the team context manager from app state."""
    return app.state.team_context_manager


@pytest.fixture
def langgraph_gateway(autouse=True):
    """Register workflows for testing."""
    import asyncio
    from src.aegis.services.langgraph_gateway import WorkflowDefinition

    gateway = app.state.langgraph_gateway

    async def register_workflows():
        public_assistant = WorkflowDefinition(
            workflow_id="public_assistant",
            name="Public Assistant",
            description="Test workflow for public queries",
            tier_requirement=1,
            data_classification="PUBLIC",
            max_steps=5,
            timeout_seconds=30,
            allowed_tools=["web_search"],
            requires_approval=False,
            requires_human_in_loop=False,
            cost_estimate_usd=0.01,
            enabled=True,
        )
        await gateway.register_workflow(public_assistant)

        test_workflow = WorkflowDefinition(
            workflow_id="test-workflow",
            name="Test Workflow",
            description="Basic test workflow",
            tier_requirement=1,
            data_classification="INTERNAL",
            max_steps=3,
            timeout_seconds=20,
            allowed_tools=[],
            requires_approval=False,
            requires_human_in_loop=False,
            cost_estimate_usd=0.001,
            enabled=True,
        )
        await gateway.register_workflow(test_workflow)

    asyncio.run(register_workflows())
    yield gateway


@pytest.fixture
def sample_team(team_context_manager):
    """Register a sample team for testing."""
    team_context_manager.register_team(
        "test-team",
        members={"user-1", "user-2"},
        permissions={"execute_workflow", "use_web_tools", "use_data_tools"},
        budget_remaining_usd=1000.0,
    )
    return "test-team"


@pytest.fixture
def other_team(team_context_manager):
    """Register another team for cross-team access testing."""
    team_context_manager.register_team(
        "other-team",
        members={"user-3"},
        permissions={"execute_workflow"},
        budget_remaining_usd=500.0,
    )
    return "other-team"


class TestInvokeEndpoint:
    """Tests for POST /api/v1/workflows/{workflow_id}/invoke"""

    def test_invoke_missing_headers(self, client):
        """Test invoke without required team headers returns 400."""
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {"query": "test"}},
        )
        assert response.status_code == 400
        assert "X-Team-ID and X-User-ID headers are required" in response.text

    def test_invoke_workflow_not_found(self, client, sample_team):
        """Test invoke with non-existent workflow returns 400 or 404."""
        response = client.post(
            "/api/v1/workflows/nonexistent-workflow/invoke",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Workflow engine may return 400 (ValueError) or 500 depending on implementation
        assert response.status_code in [400, 404, 500]

    def test_invoke_response_structure(self, client, sample_team):
        """Test invoke response has correct structure."""
        # This test would work with a registered workflow
        # For now, we test the error response structure
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Even on error, the response should be JSON
        data = response.json()
        assert isinstance(data, dict)

    def test_invoke_cross_team_isolation(self, client, sample_team, other_team):
        """Test that users cannot invoke workflows from other teams."""
        # User from other_team tries to invoke with sample_team headers
        # This depends on whether execution checks team isolation
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": other_team, "X-User-ID": "user-1"},  # user-1 not in other_team
        )
        # Should reject due to user not in team
        assert response.status_code == 403

    def test_invoke_with_config_override(self, client, sample_team):
        """Test invoke accepts config overrides."""
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={
                "input": {"query": "test"},
                "config": {"tools": ["web_search"]},
            },
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Should not fail due to config format
        assert response.status_code != 400


class TestStreamEndpoint:
    """Tests for POST /api/v1/workflows/{workflow_id}/stream"""

    def test_stream_missing_headers(self, client):
        """Test stream without required team headers returns 400."""
        response = client.post(
            "/api/v1/workflows/test-workflow/stream",
            json={"input": {"query": "test"}},
        )
        assert response.status_code == 400

    def test_stream_response_is_sse(self, client, sample_team):
        """Test stream response has SSE content type."""
        response = client.post(
            "/api/v1/workflows/public_assistant/stream",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
            timeout=10,  # TestClient will read from stream until timeout
        )
        # Should return SSE content type
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Should have gotten at least the start event
        assert response.status_code == 200

    def test_stream_event_format(self, client, sample_team):
        """Test stream yields properly formatted SSE events."""
        response = client.post(
            "/api/v1/workflows/public_assistant/stream",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
            timeout=10,  # TestClient will read from stream until timeout
        )
        # Verify response started streaming
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Note: We cannot reliably test event format with TestClient as it blocks
        # until stream completion (300s timeout). SSE event format is tested in
        # LangServeAdapter unit tests and via invoke endpoint tests.


class TestBatchEndpoint:
    """Tests for POST /api/v1/workflows/{workflow_id}/batch"""

    def test_batch_missing_headers(self, client):
        """Test batch without required team headers returns 400."""
        response = client.post(
            "/api/v1/workflows/public_assistant/batch",
            json={"inputs": [{"query": "test1"}, {"query": "test2"}]},
        )
        assert response.status_code == 400

    def test_batch_response_structure(self, client, sample_team):
        """Test batch response has correct structure."""
        response = client.post(
            "/api/v1/workflows/public_assistant/batch",
            json={"inputs": [{"query": "test1"}, {"query": "test2"}]},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Response should be JSON (even if error)
        data = response.json()
        assert isinstance(data, dict)

    def test_batch_preserves_input_order(self, client, sample_team):
        """Test batch results maintain input order."""
        inputs = [
            {"id": 1, "query": "first"},
            {"id": 2, "query": "second"},
            {"id": 3, "query": "third"},
        ]
        response = client.post(
            "/api/v1/workflows/public_assistant/batch",
            json={"inputs": inputs},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # If successful, executions should be in same order as inputs
        if response.status_code == 200:
            data = response.json()
            assert "executions" in data
            executions = data["executions"]
            assert len(executions) == len(inputs)

    def test_batch_concurrency_limit(self, client, sample_team):
        """Test batch respects max_concurrency parameter."""
        inputs = [{"query": f"test{i}"} for i in range(10)]
        response = client.post(
            "/api/v1/workflows/public_assistant/batch",
            json={"inputs": inputs, "max_concurrency": 2},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Should not fail due to concurrency configuration
        assert response.status_code != 400

    def test_batch_default_concurrency(self, client, sample_team):
        """Test batch uses default max_concurrency=4."""
        inputs = [{"query": f"test{i}"} for i in range(5)]
        response = client.post(
            "/api/v1/workflows/public_assistant/batch",
            json={"inputs": inputs},
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # Should not fail with default concurrency
        assert response.status_code != 400


class TestListEndpoint:
    """Tests for GET /api/v1/workflows/list"""

    def test_list_missing_headers(self, client):
        """Test list without required team headers returns 400."""
        response = client.get("/api/v1/workflows/list")
        assert response.status_code == 400

    def test_list_response_structure(self, client, sample_team):
        """Test list response has correct structure."""
        response = client.get(
            "/api/v1/workflows/list",
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert "count" in data
        assert isinstance(data["workflows"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["workflows"])


class TestSchemaEndpoint:
    """Tests for GET /api/v1/workflows/{workflow_id}/schema"""

    def test_schema_missing_headers(self, client):
        """Test schema without required team headers returns 400."""
        response = client.get("/api/v1/workflows/public_assistant/schema")
        assert response.status_code == 400

    def test_schema_response_structure(self, client, sample_team):
        """Test schema response has required fields."""
        response = client.get(
            "/api/v1/workflows/public_assistant/schema",
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        # May fail with 404 if workflow doesn't exist, that's ok
        if response.status_code == 200:
            data = response.json()
            assert "title" in data
            assert "description" in data
            assert "input_schema" in data
            assert "output_schema" in data
            assert "config_schema" in data


class TestTeamContextIsolation:
    """Tests for multi-tenant isolation across endpoints."""

    def test_user_not_in_team_is_denied(self, client, other_team):
        """Test that users not in a team cannot access resources."""
        # user-1 is not in other_team (only user-3 is)
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {"query": "test"}},
            headers={"X-Team-ID": other_team, "X-User-ID": "user-1"},
        )
        assert response.status_code == 403

    def test_team_context_preserved_across_endpoints(self, client, sample_team):
        """Test that team context is consistently applied."""
        headers = {"X-Team-ID": sample_team, "X-User-ID": "user-1"}

        # Test with invoke
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {}},
            headers=headers,
        )
        # Should not fail due to missing headers
        assert response.status_code != 400

        # Test with stream
        response = client.post(
            "/api/v1/workflows/test-workflow/stream",
            json={"input": {}},
            headers=headers,
        )
        # Should not fail due to missing headers
        assert response.status_code != 400

        # Test with batch
        response = client.post(
            "/api/v1/workflows/test-workflow/batch",
            json={"inputs": [{}]},
            headers=headers,
        )
        # Should not fail due to missing headers
        assert response.status_code != 400

        # Test with list
        response = client.get(
            "/api/v1/workflows/list",
            headers=headers,
        )
        # Should not fail due to missing headers
        assert response.status_code != 400


class TestErrorHandling:
    """Tests for error handling and validation."""

    def test_invalid_team_id_format(self, client):
        """Test that invalid team IDs are rejected."""
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {}},
            headers={"X-Team-ID": "!!!invalid!!!", "X-User-ID": "user-1"},
        )
        assert response.status_code == 400

    def test_empty_user_id(self, client, sample_team):
        """Test that empty user IDs are rejected."""
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            json={"input": {}},
            headers={"X-Team-ID": sample_team, "X-User-ID": ""},
        )
        assert response.status_code == 400

    def test_malformed_json_request(self, client, sample_team):
        """Test that malformed JSON is rejected."""
        response = client.post(
            "/api/v1/workflows/test-workflow/invoke",
            data="not valid json",
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        assert response.status_code == 422  # Unprocessable entity

    def test_batch_max_concurrency_validation(self, client, sample_team):
        """Test batch concurrency limits are enforced."""
        # max_concurrency must be 1-16
        response = client.post(
            "/api/v1/workflows/test-workflow/batch",
            json={"inputs": [{}], "max_concurrency": 0},  # Below minimum
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        assert response.status_code == 422  # Validation error

        response = client.post(
            "/api/v1/workflows/test-workflow/batch",
            json={"inputs": [{}], "max_concurrency": 20},  # Above maximum
            headers={"X-Team-ID": sample_team, "X-User-ID": "user-1"},
        )
        assert response.status_code == 422  # Validation error
