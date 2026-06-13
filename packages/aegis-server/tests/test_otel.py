"""OTel + Prometheus observability tests (D16).

Gate: DC uv run pytest packages/aegis-server -q -k otel
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
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


def _make_client_with_exporter() -> tuple[TestClient, str, InMemorySpanExporter]:
    """Return (client, api_key, span_exporter) with per-test OTel exporter.

    Creates an isolated ``TracerProvider`` so tests don't share global state.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("aegis.server")

    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="otel response")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="otel-user", team="t")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store, tracer=tracer)
    return TestClient(app, raise_server_exceptions=True), api_key, exporter


# ---------------------------------------------------------------------------
# OTel span tests
# ---------------------------------------------------------------------------


def test_otel_run_emits_aegis_run_span() -> None:
    """POST /v1/runs emits an 'aegis.run' span."""
    client, api_key, exporter = _make_client_with_exporter()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "otel test"}]},
    )
    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]
    assert "aegis.run" in span_names, f"Expected 'aegis.run' span, got: {span_names}"


def test_otel_span_has_route_attribute() -> None:
    """The 'aegis.run' span carries the run.route attribute."""
    client, api_key, exporter = _make_client_with_exporter()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "hi"}], "route": "default"},
    )
    spans = exporter.get_finished_spans()
    run_spans = [s for s in spans if s.name == "aegis.run"]
    assert run_spans, "No aegis.run span found"
    span = run_spans[0]
    assert span.attributes is not None
    assert span.attributes.get("run.route") == "default"


def test_otel_span_has_run_id_attribute() -> None:
    """The 'aegis.run' span carries the run.id attribute."""
    client, api_key, exporter = _make_client_with_exporter()
    resp = client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    run_id = resp.json()["run_id"]
    spans = exporter.get_finished_spans()
    run_spans = [s for s in spans if s.name == "aegis.run"]
    assert run_spans
    assert run_spans[0].attributes is not None
    assert run_spans[0].attributes.get("run.id") == run_id


def test_otel_span_has_principal_id_attribute() -> None:
    """The 'aegis.run' span carries the run.principal_id attribute."""
    client, api_key, exporter = _make_client_with_exporter()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    spans = exporter.get_finished_spans()
    run_spans = [s for s in spans if s.name == "aegis.run"]
    assert run_spans
    assert run_spans[0].attributes is not None
    assert run_spans[0].attributes.get("run.principal_id") == "otel-user"


def test_otel_span_has_run_status_attribute() -> None:
    """The 'aegis.run' span carries run.status after the run completes."""
    client, api_key, exporter = _make_client_with_exporter()
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    spans = exporter.get_finished_spans()
    run_spans = [s for s in spans if s.name == "aegis.run"]
    assert run_spans
    assert run_spans[0].attributes is not None
    assert "run.status" in run_spans[0].attributes


# ---------------------------------------------------------------------------
# Prometheus metrics tests
# ---------------------------------------------------------------------------


def test_otel_metrics_endpoint_accessible() -> None:
    """GET /metrics returns 200 with prometheus text format."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "aegis_runs_total" in resp.text


def test_otel_metrics_endpoint_exposes_run_duration() -> None:
    """GET /metrics exposes aegis_run_duration_seconds."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="m-user", team="t")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    client = TestClient(app, raise_server_exceptions=False)

    # Run a request so the histogram has data
    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "metrics test"}]},
    )

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "aegis_run_duration_seconds" in resp.text


def test_otel_metrics_endpoint_counts_runs() -> None:
    """aegis_runs_total increments after a pipeline run."""
    store = InMemoryRunStore()
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="cnt-user", team="t")
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    client = TestClient(app, raise_server_exceptions=False)

    client.post(
        "/v1/runs",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"messages": [{"role": "user", "content": "count test"}]},
    )

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "aegis_runs_total" in resp.text
