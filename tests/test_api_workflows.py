from __future__ import annotations

from fastapi.testclient import TestClient

from src.aegis.main import app


def _headers(team_id: str = "team-api", user_id: str = "alice") -> dict[str, str]:
    return {"X-Team-ID": team_id, "X-User-ID": user_id}


def test_workflow_list_endpoint_returns_configured_workflows():
    client = TestClient(app)
    response = client.get("/api/v1/workflows/list", headers=_headers("team-api-list"))
    assert response.status_code == 200
    data = response.json()
    workflow_ids = {workflow["workflow_id"] for workflow in data["workflows"]}
    assert {"public_assistant", "data_lookup", "restricted_code_analyst"}.issubset(workflow_ids)


def test_workflow_execute_status_and_history_endpoints():
    client = TestClient(app)
    headers = _headers("team-api-run")

    submit = client.post(
        "/api/v1/workflows/public_assistant/execute",
        headers=headers,
        json={"input_data": {"query": "What is RAG?", "max_results": 1}},
    )
    assert submit.status_code == 202
    workflow_instance_id = submit.json()["workflow_instance_id"]
    assert submit.json()["status"] == "completed"

    status = client.get(f"/api/v1/workflows/instances/{workflow_instance_id}", headers=headers)
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["status"] == "completed"
    assert status_data["team_id"] == "team-api-run"
    assert status_data["tool_calls_count"] == 1

    history = client.get(
        f"/api/v1/workflows/instances/{workflow_instance_id}/history",
        headers=headers,
    )
    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == ["user", "assistant"]


def test_workflow_status_is_team_isolated():
    client = TestClient(app)
    submit = client.post(
        "/api/v1/workflows/public_assistant/execute",
        headers=_headers("team-api-owner"),
        json={"input_data": {"query": "isolation"}},
    )
    workflow_instance_id = submit.json()["workflow_instance_id"]

    response = client.get(
        f"/api/v1/workflows/instances/{workflow_instance_id}",
        headers=_headers("team-api-other"),
    )

    assert response.status_code == 404


def test_workflow_queue_endpoint_returns_queue_id():
    client = TestClient(app)
    response = client.post(
        "/api/v1/workflows/public_assistant/execute",
        headers=_headers("team-api-queue"),
        json={"input_data": {"query": "queue me"}, "queue": True, "priority": 9},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["queue_id"]


def test_tools_api_lists_and_validates_tools():
    client = TestClient(app)
    headers = _headers("team-api-tools")

    list_response = client.get("/api/v1/tools/list", headers=headers)
    assert list_response.status_code == 200
    tool_names = {tool["name"] for tool in list_response.json()["tools"]}
    assert "web_search" in tool_names

    validate = client.post(
        "/api/v1/tools/web_search/validate",
        headers=headers,
        json={"args": {"query": "aegis", "max_results": 1}},
    )
    assert validate.status_code == 200
    assert validate.json()["valid"] is True


def test_direct_tool_execution_requires_admin_permission():
    client = TestClient(app)
    response = client.post(
        "/api/v1/tools/web_search/execute",
        headers=_headers("team-api-no-admin"),
        json={"args": {"query": "aegis"}},
    )
    assert response.status_code == 403


def test_conversations_api_lists_exports_and_archives():
    client = TestClient(app)
    headers = _headers("team-api-conversations")
    submit = client.post(
        "/api/v1/workflows/public_assistant/execute",
        headers=headers,
        json={"input_data": {"query": "conversation"}},
    )
    workflow_instance_id = submit.json()["workflow_instance_id"]
    status = client.get(f"/api/v1/workflows/instances/{workflow_instance_id}", headers=headers).json()
    conversation_id = status["conversation_id"]

    listed = client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200
    assert any(item["conversation_id"] == conversation_id for item in listed.json()["conversations"])

    exported = client.post(
        f"/api/v1/conversations/{conversation_id}/export",
        headers=headers,
        params={"format": "markdown"},
    )
    assert exported.status_code == 200
    assert "**user:**" in exported.json()["content"]

    delete = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert delete.status_code == 204
