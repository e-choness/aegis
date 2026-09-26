"""Tests for the showcase page backend (Step 16)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from starlette.testclient import TestClient

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.store.run_store import InMemoryRunStore

if TYPE_CHECKING:
    from aegis_core.pipeline.protocol import PipelineNode

try:
    from aegis_pack_pii import PiiMaskNode, PiiUnmaskNode
except ImportError:
    PiiMaskNode = None  # type: ignore[misc,assignment]
    PiiUnmaskNode = None  # type: ignore[misc,assignment]


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider(complete_response="hello from aegis")


@pytest.fixture
def executor(fake_provider: FakeProvider) -> PipelineExecutor:
    ex = PipelineExecutor()
    ingress_nodes = (
        cast("list[PipelineNode]", [PiiMaskNode()]) if PiiMaskNode is not None else []
    )
    egress_nodes = (
        cast("list[PipelineNode]", [PiiUnmaskNode()]) if PiiUnmaskNode is not None else []
    )
    ex.register("default", provider=fake_provider, ingress=ingress_nodes, egress=egress_nodes)
    return ex


@pytest.fixture
def client(executor: PipelineExecutor) -> TestClient:
    app = create_app(
        executor,
        no_auth=True,
        run_store=InMemoryRunStore(),
        demo_mode=True,
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


@pytest.mark.skipif(
    PiiMaskNode is None, reason="PII pack not installed (requires [pii] extra)"
)
def test_showcase_pii_masking(client: TestClient) -> None:
    """Step 17 check: PII in prompt triggers mask_map populated (mask/unmask demo)."""
    r = client.post(
        "/showcase/api/invoke",
        json={"prompt": "My email is user@example.com and SSN is 123-45-6789", "route": "default"},
    )
    assert r.status_code == 200
    body = r.json()
    mask_map = body.get("mask_map", {})
    assert "<EMAIL_ADDRESS_0>" in mask_map, f"Expected masked email, got: {mask_map}"
    assert mask_map["<EMAIL_ADDRESS_0>"] == "user@example.com"
    # Check events include mask node
    event_types = [e.get("event_type") for e in body.get("events", [])]
    assert "node_start" in event_types
    assert "node_end" in event_types


def test_showcase_rate_limit_returns_429(client: TestClient) -> None:
    """Demo mode: an 11th API request within a minute from one visitor gets 429."""
    statuses = [
        client.post("/showcase/api/invoke", json={"prompt": f"r{i}", "route": "default"}).status_code
        for i in range(11)
    ]
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


def test_demo_rate_limit_is_per_forwarded_visitor(client: TestClient) -> None:
    """Behind a proxy, visitors are told apart by X-Forwarded-For."""

    def run(ip: str) -> int:
        body = {"messages": [{"role": "user", "content": "hi"}]}
        return client.post("/v1/runs", json=body, headers={"X-Forwarded-For": ip}).status_code

    for i in range(10):
        assert run(f"203.0.113.7, 10.0.0.{i}") == 200
    assert run("203.0.113.7") == 429
    assert run("198.51.100.2") == 200


def test_demo_reads_and_pages_are_never_limited(client: TestClient) -> None:
    """The showcase page polls runs/models; reads must not consume the quota."""
    for _ in range(15):
        assert client.get("/v1/health").status_code == 200
        assert client.get("/showcase/api/runs").status_code == 200
        assert client.get("/v1/models").status_code == 200
    assert client.get("/showcase").status_code == 200


def test_demo_hourly_cap_is_rolling() -> None:
    """The global cap is a rolling window, not a lifetime counter."""
    import asyncio

    from aegis_server.routes import showcase as sc

    calls: list[str] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["path"])

    mw = sc.DemoRateLimitMiddleware(app, per_minute=100, per_hour=2)  # type: ignore[arg-type]
    scope = {"type": "http", "method": "POST", "path": "/v1/runs", "headers": [], "client": ("1.2.3.4", 1)}
    asyncio.run(mw(scope, None, None))  # type: ignore[arg-type]
    asyncio.run(mw(scope, None, None))  # type: ignore[arg-type]
    assert len(calls) == 2
    mw._all[0] -= 3601  # the first request ages out of the window
    asyncio.run(mw(scope, None, None))  # type: ignore[arg-type]
    assert len(calls) == 3

