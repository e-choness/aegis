"""Tests for the showcase page backend (Step 16)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth.none import NoneAuthenticator
from aegis_server.store.run_store import InMemoryRunStore


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider(complete_response="hello from aegis")


@pytest.fixture
def executor(fake_provider: FakeProvider) -> PipelineExecutor:
    ex = PipelineExecutor()
    ex.register("default", provider=fake_provider)
    return ex


@pytest.fixture
def client(executor: PipelineExecutor) -> TestClient:
    app = create_app(
        executor,
        no_auth=True,
        run_store=InMemoryRunStore(),
    )
    return TestClient(app, raise_server_exceptions=True)


def test_showcase_page_loads(client: TestClient) -> None:
    r = client.get("/showcase")
    assert r.status_code == 200
    assert "Pipeline Showcase" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_showcase_invoke_returns_run(client: TestClient) -> None:
    r = client.post(
        "/showcase/api/invoke",
        json={"prompt": "My email is user@example.com", "route": "default"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert body["status"] in {"running", "completed"}
    assert "events" in body
    assert "mask_map" in body


def test_showcase_invoke_missing_route(client: TestClient) -> None:
    r = client.post(
        "/showcase/api/invoke",
        json={"prompt": "hello", "route": "nonexistent"},
    )
    assert r.status_code == 404
    assert "nonexistent" in (r.json()["detail"])


def test_showcase_runs_after_invoke(client: TestClient) -> None:
    client.post(
        "/showcase/api/invoke",
        json={"prompt": "list the runs", "route": "default"},
    )
    r = client.get("/showcase/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert "runs" in body
    assert len(body["runs"]) >= 1


def test_showcase_resume_requires_paused_run(client: TestClient) -> None:
    import uuid

    r = client.post(
        f"/showcase/api/runs/{uuid.uuid4()}/resume",
        json={"decision": "approved"},
    )
    assert r.status_code == 404


def test_showcase_route_not_in_openapi_schema(client: TestClient) -> None:
    schema_resp = client.get("/openapi.json")
    paths = schema_resp.json()["paths"]
    assert "/showcase" not in paths
    assert "/showcase/api/invoke" not in paths

