"""Tests for GET /v1/health (Phase 0)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


def test_health_ok(client_no_auth: TestClient) -> None:
    resp = client_no_auth.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_health_no_digest_when_not_set(client_no_auth: TestClient) -> None:
    resp = client_no_auth.get("/v1/health")
    body = resp.json()
    assert body["config_digest"] is None
    assert body["config_path"] is None


def test_health_returns_digest(client_with_digest: TestClient) -> None:
    resp = client_with_digest.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["config_digest"] == "sha256:abc123"
    assert body["config_path"] == "/etc/aegis/aegis.yaml"


def test_health_unauthenticated_allowed(client_with_digest: TestClient) -> None:
    """Health endpoint must be reachable without auth headers."""
    resp = client_with_digest.get("/v1/health")
    assert resp.status_code == 200
