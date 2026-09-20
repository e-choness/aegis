"""POST /v1/runs — Principal attached to run result."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_run_returns_principal_id(client: TestClient, valid_key: str) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["principal_id"] == "test-user"
    assert data["status"] in ("completed", "running")
    assert isinstance(data["events"], list)
    assert len(data["events"]) > 0


def test_run_response_has_content(client: TestClient, valid_key: str) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"messages": [{"role": "user", "content": "hello"}], "route": "default"},
    )
    assert resp.status_code == 200
    assert resp.json()["response"] == "hello from aegis"


def test_run_unknown_route_returns_404(client: TestClient, valid_key: str) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"messages": [{"role": "user", "content": "hi"}], "route": "no-such-route"},
    )
    assert resp.status_code == 404


def test_run_record_persists_events_and_digest(client_with_digest: TestClient) -> None:
    """POST /v1/runs then GET /v1/runs/{id} must include events and config_digest (Phase 1)."""
    post_resp = client_with_digest.post(
        "/v1/runs",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert post_resp.status_code == 200
    run_id = post_resp.json()["run_id"]

    get_resp = client_with_digest.get(f"/v1/runs/{run_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert isinstance(data["events"], list)
    assert "config_digest" in data
    assert data["config_digest"] == "sha256:abc123"
