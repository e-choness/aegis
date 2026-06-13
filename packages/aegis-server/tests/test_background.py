"""Background run tests — background: true flag on POST /v1/runs (D14).

Gate: DC uv run pytest packages/aegis-server -q -k background
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.run_store import InMemoryRunStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> tuple[FastAPI, str]:
    """Build a simple no-guard app and return (app, api_key)."""
    fake = FakeProvider(complete_response="background result")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="test-user", team="test-team")
    store = InMemoryRunStore()
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    return app, api_key


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_background_run_returns_pending_status() -> None:
    """POST /v1/runs with background=true responds immediately with status=pending."""
    app, api_key = _make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hi"}], "background": True},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert "run_id" in data
    assert data["response"] is None


@pytest.mark.asyncio
async def test_background_run_eventually_completes() -> None:
    """After a background run is submitted, polling GET /v1/runs/{id} eventually shows completed."""
    app, api_key = _make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}], "background": True},
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        assert resp.json()["status"] == "pending"

        # Allow the background task to execute
        await asyncio.sleep(0.1)

        poll = await client.get(
            f"/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    assert poll.status_code == 200
    assert poll.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_background_run_stored_in_run_store() -> None:
    """A background run creates a RunRecord immediately (status=pending → running → completed)."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="stored")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="alice", team="t")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "store test"}], "background": True},
        )
        run_id = resp.json()["run_id"]
        # Record exists with pending status immediately after POST
        record = await store.get(run_id)
        assert record is not None

        await asyncio.sleep(0.1)
        record_after = await store.get(run_id)

    assert record_after is not None
    assert record_after.status == "completed"


@pytest.mark.asyncio
async def test_background_run_route_defaults_to_default() -> None:
    """Background run with no explicit route uses 'default'."""
    app, api_key = _make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hi"}], "background": True},
        )
        run_id = resp.json()["run_id"]
        await asyncio.sleep(0.1)
        poll = await client.get(
            f"/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    assert poll.json()["route"] == "default"


@pytest.mark.asyncio
async def test_background_false_is_synchronous() -> None:
    """background=False (default) returns a completed response synchronously."""
    app, api_key = _make_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "sync"}], "background": False},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["response"] == "background result"
