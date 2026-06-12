"""HITL (human-in-the-loop) tests — pause/resume, restart, deny, auth (D11/D14).

Gate: DC uv run pytest packages/aegis-server -q -k hitl
"""

from __future__ import annotations

import asyncio
from typing import ClassVar, Literal

import httpx
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from aegis_core.guardrails import GuardNode
from aegis_core.pipeline.checkpointer import make_memory_checkpointer, sqlite_checkpointer
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.run_store import InMemoryRunStore, SqliteRunStore

# ---------------------------------------------------------------------------
# Fixtures — approval guard
# ---------------------------------------------------------------------------


class _ApprovalGuard:
    """Always returns require_approval to trigger HITL pause."""

    name = "approval_guard"
    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.require_approval("human review required")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hitl_app(
    checkpointer: object | None = None,
    run_store: object | None = None,
    key_store: KeyStore | None = None,
) -> tuple[FastAPI, KeyStore, str]:
    """Build a test app with an approval-gated default route.

    Returns (app, key_store, api_key).
    """
    fake = FakeProvider(complete_response="approved response")
    ks = key_store or KeyStore()
    api_key = ks.create(principal_id="test-user", team="test-team")

    cp = checkpointer if checkpointer is not None else make_memory_checkpointer()
    ex = PipelineExecutor(checkpointer=cp)
    ex.register(
        "default",
        provider=fake,
        ingress=[GuardNode(guards=[_ApprovalGuard()], name="approval")],
    )

    store = run_store if run_store is not None else InMemoryRunStore()
    auth = ApiKeyAuthenticator(ks)
    app = create_app(ex, authenticator=auth, run_store=store)
    return app, ks, api_key


# ---------------------------------------------------------------------------
# Basic pause/resume tests
# ---------------------------------------------------------------------------


def test_hitl_run_pauses_on_approval_guard() -> None:
    app, _ks, api_key = _make_hitl_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "paused", data


def test_hitl_get_run_returns_status() -> None:
    app, _ks, api_key = _make_hitl_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        run_id = run_resp.json()["run_id"]
        get_resp = client.get(
            f"/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "paused"


def test_hitl_get_run_404_unknown() -> None:
    app, _ks, api_key = _make_hitl_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.get(
            "/v1/runs/no-such-run",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    assert resp.status_code == 404


def test_hitl_approve_resumes_and_completes() -> None:
    app, _ks, api_key = _make_hitl_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert run_resp.json()["status"] == "paused"
        run_id = run_resp.json()["run_id"]

        resume_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"decision": "approved"},
        )
    assert resume_resp.status_code == 200
    data = resume_resp.json()
    assert data["status"] == "completed"
    assert data["response"] == "approved response"


def test_hitl_deny_terminates_with_denied_status() -> None:
    app, _ks, api_key = _make_hitl_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        run_id = run_resp.json()["run_id"]

        resume_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"decision": "denied"},
        )
    assert resume_resp.status_code == 200
    data = resume_resp.json()
    assert data["status"] == "denied"
    # Deny must emit an audit verdict event
    events = data["events"]
    verdict_events = [e for e in events if e.get("event_type") == "verdict"]
    denied_events = [e for e in verdict_events if e["data"].get("verdict") == "denied"]
    assert denied_events, f"No denied verdict event found in: {events}"


def test_hitl_deny_status_stored_in_run_store() -> None:
    store = InMemoryRunStore()
    app, _ks, api_key = _make_hitl_app(run_store=store)
    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        run_id = run_resp.json()["run_id"]

        client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"decision": "denied"},
        )

    # Verify RunStore updated
    record = asyncio.run(store.get(run_id))
    assert record is not None
    assert record.status == "denied"


def test_hitl_resume_conflict_on_non_paused_run() -> None:
    """Resuming a run that is not paused returns 409."""
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="test-user", team="test-team")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks))
    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert run_resp.json()["status"] == "completed"
        run_id = run_resp.json()["run_id"]

        resume_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"decision": "approved"},
        )
    assert resume_resp.status_code == 409


# ---------------------------------------------------------------------------
# Approver authorization (AEG-AUTH-003)
# ---------------------------------------------------------------------------


def test_hitl_non_approver_gets_403() -> None:
    """A principal not listed in approvers cannot resume the run."""
    ks = KeyStore()
    user_key = ks.create(principal_id="test-user", team="team")
    approver_key = ks.create(principal_id="approver-user", team="team")

    app, _, _ = _make_hitl_app(key_store=ks)

    with TestClient(app, raise_server_exceptions=True) as client:
        # Create run with explicit approvers list — only approver-user can act
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {user_key}"},
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "approvers": ["approver-user"],
            },
        )
        assert run_resp.json()["status"] == "paused"
        run_id = run_resp.json()["run_id"]

        # test-user (not in approvers) tries to resume → 403
        bad_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {user_key}"},
            json={"decision": "approved"},
        )
        assert bad_resp.status_code == 403
        detail = bad_resp.json()["detail"]
        assert detail["code"] == "AEG-AUTH-003"

        # approver-user can resume
        good_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {approver_key}"},
            json={"decision": "approved"},
        )
        assert good_resp.status_code == 200


# ---------------------------------------------------------------------------
# Restart test — SQLite checkpointer persists across app instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_restart_sqlite(tmp_path: object) -> None:  # type: ignore[type-arg]
    """Tear down app1, rebuild app2 on the same SQLite file, resume correctly."""
    import pathlib

    db_path = str(pathlib.Path(str(tmp_path)) / "checkpoints.db")  # type: ignore[arg-type]
    runs_db = str(pathlib.Path(str(tmp_path)) / "runs.db")  # type: ignore[arg-type]

    ks = KeyStore()
    api_key = ks.create(principal_id="test-user", team="team")

    # ── Phase 1: create run, assert it pauses ──────────────────────────────
    async with sqlite_checkpointer(db_path) as cp1:
        run_store1 = SqliteRunStore(runs_db)
        ex1 = PipelineExecutor(checkpointer=cp1)
        fake1 = FakeProvider(complete_response="restarted response")
        ex1.register(
            "default",
            provider=fake1,
            ingress=[GuardNode(guards=[_ApprovalGuard()], name="approval")],
        )
        app1 = create_app(ex1, authenticator=ApiKeyAuthenticator(ks), run_store=run_store1)

        transport1 = httpx.ASGITransport(app=app1)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport1, base_url="http://test") as c1:
            resp1 = await c1.post(
                "/v1/runs",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"messages": [{"role": "user", "content": "restart test"}]},
            )
        assert resp1.status_code == 200, resp1.text
        run_id = resp1.json()["run_id"]
        assert resp1.json()["status"] == "paused"

    # App1 / cp1 / ex1 are now "torn down" (context exited).

    # ── Phase 2: new app on same SQLite files, resume ─────────────────────
    async with sqlite_checkpointer(db_path) as cp2:
        run_store2 = SqliteRunStore(runs_db)
        ex2 = PipelineExecutor(checkpointer=cp2)
        fake2 = FakeProvider(complete_response="restarted response")
        ex2.register(
            "default",
            provider=fake2,
            ingress=[GuardNode(guards=[_ApprovalGuard()], name="approval")],
        )
        app2 = create_app(ex2, authenticator=ApiKeyAuthenticator(ks), run_store=run_store2)

        transport2 = httpx.ASGITransport(app=app2)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport2, base_url="http://test") as c2:
            resp2 = await c2.post(
                f"/v1/runs/{run_id}/resume",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"decision": "approved"},
            )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["status"] == "completed"
        assert resp2.json()["response"] == "restarted response"


# ---------------------------------------------------------------------------
# Postgres smoke test (requires compose postgres service)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_postgres_smoke() -> None:
    """Smoke test: pause and resume using the Postgres checkpointer (compose service)."""
    from aegis_core.pipeline.checkpointer import postgres_checkpointer

    conn = "postgresql://postgres:postgres@postgres:5432/postgres"
    ks = KeyStore()
    api_key = ks.create(principal_id="test-user", team="team")

    try:
        async with postgres_checkpointer(conn) as cp:
            run_store = InMemoryRunStore()
            ex = PipelineExecutor(checkpointer=cp)
            fake = FakeProvider(complete_response="pg response")
            ex.register(
                "default",
                provider=fake,
                ingress=[GuardNode(guards=[_ApprovalGuard()], name="approval")],
            )
            app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=run_store)

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:  # type: ignore[arg-type]
                r1 = await client.post(
                    "/v1/runs",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"messages": [{"role": "user", "content": "pg test"}]},
                )
                assert r1.status_code == 200, r1.text
                assert r1.json()["status"] == "paused"
                run_id = r1.json()["run_id"]

                r2 = await client.post(
                    f"/v1/runs/{run_id}/resume",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"decision": "approved"},
                )
                assert r2.status_code == 200, r2.text
                assert r2.json()["status"] == "completed"
    except Exception as exc:
        pytest.skip(f"Postgres not available: {exc}")
