"""Audit API tests — GET /v1/audit (D14).

Gate: DC uv run pytest packages/aegis-server -q -k audit
"""

from __future__ import annotations

from starlette.testclient import TestClient

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.run_store import InMemoryRunStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> tuple[TestClient, str, str, InMemoryRunStore]:
    """Return (client, alice_key, bob_key, run_store)."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ex.register("other", provider=fake)
    ks = KeyStore()
    alice_key = ks.create(principal_id="alice", team="t")
    bob_key = ks.create(principal_id="bob", team="t")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    return TestClient(app, raise_server_exceptions=True), alice_key, bob_key, store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_audit_empty_returns_empty_list() -> None:
    """GET /v1/audit on a fresh store returns an empty list."""
    client, alice_key, _bob_key, _store = _make_client()
    resp = client.get("/v1/audit", headers={"Authorization": f"Bearer {alice_key}"})
    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_audit_returns_completed_runs() -> None:
    """Runs made via POST /v1/runs appear in GET /v1/audit."""
    client, alice_key, _bob_key, _store = _make_client()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    resp = client.get("/v1/audit", headers={"Authorization": f"Bearer {alice_key}"})
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["principal_id"] == "alice"


def test_audit_filter_by_principal() -> None:
    """?principal= filter returns only matching runs."""
    client, alice_key, bob_key, _store = _make_client()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "a"}]},
    )
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"messages": [{"role": "user", "content": "b"}]},
    )

    resp = client.get(
        "/v1/audit?principal=alice",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    runs = resp.json()["runs"]
    assert all(r["principal_id"] == "alice" for r in runs)
    assert len(runs) == 1


def test_audit_filter_by_route() -> None:
    """?route= filter returns only runs on that route."""
    client, alice_key, _bob_key, _store = _make_client()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "x"}], "route": "default"},
    )
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "y"}], "route": "other"},
    )

    resp = client.get(
        "/v1/audit?route=other",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["route"] == "other"


def test_audit_filter_by_principal_and_route() -> None:
    """Combined ?principal=&route= filters AND together."""
    client, alice_key, bob_key, _store = _make_client()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "a"}], "route": "default"},
    )
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "a"}], "route": "other"},
    )
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {bob_key}"},
        json={"messages": [{"role": "user", "content": "b"}], "route": "default"},
    )

    resp = client.get(
        "/v1/audit?principal=alice&route=default",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["principal_id"] == "alice"
    assert runs[0]["route"] == "default"


def test_audit_response_includes_created_at() -> None:
    """Audit entries include a created_at timestamp."""
    client, alice_key, _bob_key, _store = _make_client()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    resp = client.get("/v1/audit", headers={"Authorization": f"Bearer {alice_key}"})
    run = resp.json()["runs"][0]
    assert "created_at" in run
    assert run["created_at"]  # non-empty


def test_audit_since_filter_excludes_earlier_runs() -> None:
    """?since= ISO-8601 filter excludes runs created before the cutoff."""
    from datetime import UTC, datetime, timedelta

    client, alice_key, _bob_key, _store = _make_client()
    # Create a run
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {alice_key}"},
        json={"messages": [{"role": "user", "content": "old"}]},
    )

    # since = far future — no runs match
    future = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat()
    resp = client.get(
        f"/v1/audit?since={future}",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    assert resp.json()["runs"] == []

    # since = past — all runs match
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    resp2 = client.get(
        f"/v1/audit?since={past}",
        headers={"Authorization": f"Bearer {alice_key}"},
    )
    assert len(resp2.json()["runs"]) == 1


def test_audit_requires_authentication() -> None:
    """GET /v1/audit without Authorization header returns 401."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/v1/audit")
    assert resp.status_code == 401
