"""Auth middleware tests — 401 paths."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_no_auth_header_returns_401(client: TestClient) -> None:
    resp = client.post("/v1/runs", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401
    assert resp.json()["code"] == "AEG-AUTH-001"


def test_bad_key_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": "Bearer aeg-" + "0" * 64},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


def test_non_bearer_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


def test_valid_key_returns_200(client: TestClient, valid_key: str) -> None:
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
