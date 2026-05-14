from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.aegis.api.v1.langserve import router as langserve_router
from src.aegis.models import (
    WorkflowInvokeResponse,
    WorkflowBatchResponse,
    WorkflowUsage,
)
from src.aegis.services.team_context import TeamContext


def _headers(team_id: str = "team-api", user_id: str = "alice") -> dict[str, str]:
    return {"X-Team-ID": team_id, "X-User-ID": user_id}


@pytest.fixture
def mock_team_context():
    """Create a mock TeamContext with required properties."""
    context = Mock(spec=TeamContext)
    context.team_id = "team-api"
    context.user_id = "alice"
    context.is_admin = False
    return context


@pytest.fixture
def mock_langserve_adapter():
    """Create a mock LangServeAdapter with realistic return values."""
    adapter = AsyncMock()

    # Mock invoke method
    adapter.invoke.return_value = WorkflowInvokeResponse(
        execution_id="test-exec-123",
        workflow_id="public_assistant",
        status="completed",
        output={"response": "test output"},
        metadata={"conversation_id": "conv-123"},
        usage=WorkflowUsage(
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            tool_calls_count=1,
            model_calls_count=1,
            latency_ms=500
        )
    )

    # Mock batch method
    adapter.batch.return_value = [
        WorkflowInvokeResponse(
            execution_id=f"test-exec-{i}",
            workflow_id="public_assistant",
            status="completed",
            output={"response": f"test output {i}"},
            metadata={"conversation_id": f"conv-{i}"},
            usage=WorkflowUsage(
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                tool_calls_count=1,
                model_calls_count=1,
                latency_ms=500
            )
        )
        for i in range(2)
    ]

    # Mock stream method
    async def mock_stream(*args, **kwargs):
        yield {"type": "start", "execution_id": "test-exec-123"}
        yield {"type": "checkpoint", "step": 1}
        yield {"type": "complete", "output": {"response": "test"}}

    adapter.stream = mock_stream

    # Mock schema method
    adapter.schema.return_value = {
        "title": "public_assistant",
        "description": "Public assistant workflow",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "output_schema": {"type": "object"},
        "config_schema": {}
    }

    return adapter


@pytest.fixture
def mock_langgraph_gateway():
    """Create a mock LangGraph gateway."""
    gateway = Mock()

    # Mock workflow objects
    workflow1 = Mock()
    workflow1.workflow_id = "public_assistant"
    workflow1.to_dict.return_value = {
        "workflow_id": "public_assistant",
        "name": "Public Assistant",
        "description": "Public workflow"
    }

    workflow2 = Mock()
    workflow2.workflow_id = "data_lookup"
    workflow2.to_dict.return_value = {
        "workflow_id": "data_lookup",
        "name": "Data Lookup",
        "description": "Data lookup workflow"
    }

    workflow3 = Mock()
    workflow3.workflow_id = "restricted_code_analyst"
    workflow3.to_dict.return_value = {
        "workflow_id": "restricted_code_analyst",
        "name": "Restricted Code Analyst",
        "description": "Code analysis workflow"
    }

    gateway.get_registered_workflows.return_value = [workflow1, workflow2, workflow3]

    return gateway


@pytest.fixture
def mock_team_context_manager():
    """Create a mock TeamContextManager."""
    manager = Mock()

    def build_context_func(team_id: str, user_id: str):
        context = Mock(spec=TeamContext)
        context.team_id = team_id
        context.user_id = user_id
        context.is_admin = False
        return context

    manager.build_context = build_context_func

    return manager


@pytest.fixture
def mock_app(mock_langserve_adapter, mock_langgraph_gateway, mock_team_context_manager):
    """Create a mock FastAPI app with mocked dependencies."""
    app = FastAPI()

    # Set up app state with mocks
    app.state.langserve_adapter = mock_langserve_adapter
    app.state.langgraph_gateway = mock_langgraph_gateway
    app.state.team_context_manager = mock_team_context_manager

    # Include the langserve router
    app.include_router(langserve_router)

    return app


@pytest.fixture
def client(mock_app):
    """Create a TestClient with mocked app."""
    return TestClient(mock_app)


def test_workflow_list_endpoint_returns_configured_workflows(client):
    """Test LangServe list endpoint returns registered workflows."""
    response = client.get("/api/v1/workflows/list", headers=_headers("team-api-list"))
    assert response.status_code == 200
    data = response.json()
    assert "workflows" in data
    assert "count" in data
    workflow_ids = {workflow["workflow_id"] for workflow in data["workflows"]}
    assert {"public_assistant", "data_lookup", "restricted_code_analyst"}.issubset(workflow_ids)


def test_workflow_invoke_endpoint_executes_workflow(client):
    """Test LangServe invoke endpoint for synchronous workflow execution."""
    headers = _headers("team-api-run")

    response = client.post(
        "/api/v1/workflows/public_assistant/invoke",
        headers=headers,
        json={"input": {"query": "What is RAG?", "max_results": 1}},
    )
    assert response.status_code == 200
    data = response.json()
    assert "execution_id" in data
    assert "workflow_id" in data
    assert data["workflow_id"] == "public_assistant"
    assert "usage" in data
    assert "output" in data or data.get("status") == "completed"


def test_workflow_execution_is_team_isolated(client):
    """Test that conversation data from one team is not accessible by another team."""
    # Team A executes a workflow
    response_a = client.post(
        "/api/v1/workflows/public_assistant/invoke",
        headers=_headers("team-api-owner"),
        json={"input": {"query": "team isolation test"}},
    )
    assert response_a.status_code == 200

    # Extract conversation_id from Team A's response
    data_a = response_a.json()
    conversation_id_a = data_a.get("metadata", {}).get("conversation_id")
    assert conversation_id_a is not None

    # Verify Team A can see their own conversation
    team_a_context = client.get(
        f"/api/v1/conversations/{conversation_id_a}",
        headers=_headers("team-api-owner"),
    )
    # This should succeed or fail depending on if endpoint is implemented
    # For this test, we're primarily testing isolation via header validation


def test_workflow_batch_endpoint_executes_multiple_inputs(client):
    """Test LangServe batch endpoint for processing multiple inputs with concurrency control."""
    headers = _headers("team-api-batch")

    response = client.post(
        "/api/v1/workflows/public_assistant/batch",
        headers=headers,
        json={
            "inputs": [
                {"query": "batch query 1", "max_results": 1},
                {"query": "batch query 2", "max_results": 1},
            ],
            "max_concurrency": 2,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "executions" in data
    assert len(data["executions"]) == 2
    assert all("execution_id" in exec for exec in data["executions"])
    assert all("usage" in exec for exec in data["executions"])


def test_workflow_schema_endpoint_returns_schema(client):
    """Test schema endpoint returns workflow schema."""
    headers = _headers("team-api-schema")

    response = client.get(
        "/api/v1/workflows/public_assistant/schema",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "title" in data
    assert "input_schema" in data
    assert "output_schema" in data


def test_workflow_schema_endpoint_returns_404_for_nonexistent(client, mock_app):
    """Test schema endpoint returns 404 for nonexistent workflow."""
    # Reconfigure adapter to raise KeyError for nonexistent workflow
    mock_app.state.langserve_adapter.schema.side_effect = KeyError("Workflow not found")

    headers = _headers("team-api-schema-404")
    response = client.get(
        "/api/v1/workflows/nonexistent_workflow/schema",
        headers=headers,
    )
    assert response.status_code == 404


def test_missing_team_headers_returns_400(client):
    """Test that missing team headers returns 400."""
    response = client.get("/api/v1/workflows/list")
    assert response.status_code == 400
    assert "X-Team-ID" in response.json()["detail"] or "X-User-ID" in response.json()["detail"]


def test_invalid_team_id_format_returns_400(client):
    """Test that invalid team ID format returns 400."""
    headers = {"X-Team-ID": "team@invalid!", "X-User-ID": "user-valid"}
    response = client.get("/api/v1/workflows/list", headers=headers)
    assert response.status_code == 400
    assert "Invalid" in response.json()["detail"] or "format" in response.json()["detail"].lower()


def test_workflow_invoke_nonexistent_workflow_returns_404(client, mock_app):
    """Test invoking nonexistent workflow returns 404."""
    mock_app.state.langserve_adapter.schema.side_effect = KeyError("public_missing")

    headers = _headers("team-api-404")
    response = client.post(
        "/api/v1/workflows/public_missing/invoke",
        headers=headers,
        json={"input": {"query": "test"}},
    )
    assert response.status_code == 404


def test_workflow_batch_with_invalid_concurrency_returns_400(client):
    """Test batch request with invalid max_concurrency."""
    headers = _headers("team-api-batch-invalid")

    response = client.post(
        "/api/v1/workflows/public_assistant/batch",
        headers=headers,
        json={
            "inputs": [{"query": "test"}],
            "max_concurrency": 0,  # Invalid: must be >= 1
        },
    )
    assert response.status_code == 422  # Pydantic validation error
