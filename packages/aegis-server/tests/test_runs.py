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
