"""OTel tracing + Prometheus metrics for aegis-server (D16).

OTel spans
----------
``configure_tracer(exporter)`` wires a :class:`TracerProvider` with the given
span exporter.  Call once at app start-up (or in tests with an
``InMemorySpanExporter``).  ``get_tracer()`` returns the configured tracer.

Prometheus metrics
------------------
``aegis_runs_total``          — Counter(route, status)
``aegis_run_duration_seconds``— Histogram(route)

``make_metrics_app()`` returns an ASGI app that exposes ``/metrics``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from prometheus_client import REGISTRY, Counter, Histogram, make_asgi_app

# ---------------------------------------------------------------------------
# OTel
# ---------------------------------------------------------------------------

_TRACER_NAME = "aegis.server"

# Module-level provider reference so tests can flush/reset it.
_provider: TracerProvider | None = None


def configure_tracer(exporter: SpanExporter | None = None) -> TracerProvider:
    """Create and register a :class:`TracerProvider`.

    Args:
        exporter: Optional span exporter.  Tests pass an
            ``InMemorySpanExporter``; production wires an OTLP exporter.
            When ``None`` the provider emits no-op spans (still traceable by
            name for structural assertions).

    Returns:
        The new :class:`TracerProvider` (also set as the global OTel provider).
    """
    global _provider
    provider = TracerProvider()
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer() -> trace.Tracer:
    """Return the aegis.server tracer (uses the global OTel provider)."""
    return trace.get_tracer(_TRACER_NAME)


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------

aegis_runs_total: Counter = Counter(
    "aegis_runs_total",
    "Total pipeline runs",
    ["route", "status"],
)

aegis_run_duration_seconds: Histogram = Histogram(
    "aegis_run_duration_seconds",
    "Pipeline run duration in seconds",
    ["route"],
)


def make_metrics_app() -> Any:
    """Return an ASGI app that exposes the Prometheus ``/metrics`` endpoint."""
    return make_asgi_app(registry=REGISTRY)


# ---------------------------------------------------------------------------
# Context manager for recording a run span + metrics
# ---------------------------------------------------------------------------


@asynccontextmanager
async def run_span(
    route: str,
    run_id: str,
    principal_id: str,
    *,
    tracer: trace.Tracer | None = None,
) -> AsyncIterator[tuple[trace.Span, list[str]]]:
    """Async context manager that wraps a pipeline run in an OTel span.

    Yields ``(span, status_holder)`` where ``status_holder`` is a
    single-element list the caller should set to the final run status
    string (e.g. ``status_holder[0] = result.status``).  Prometheus
    counters and histograms are recorded on exit using that value.

    Args:
        route: Pipeline route name.
        run_id: Unique run identifier.
        principal_id: Authenticated principal.
        tracer: OTel tracer to use.  When ``None`` uses ``get_tracer()``
            (global provider).  Pass an explicit tracer in tests to avoid
            global-state issues.

    Usage::

        async with run_span(route, run_id, principal_id) as (span, status_holder):
            result = await pipeline.run(state)
            span.set_attribute("run.status", result.status)
            status_holder[0] = result.status
    """
    _tracer = tracer if tracer is not None else get_tracer()
    start = time.monotonic()
    status_holder: list[str] = ["completed"]
    with _tracer.start_as_current_span(
        "aegis.run",
        attributes={
            "run.id": run_id,
            "run.route": route,
            "run.principal_id": principal_id,
        },
    ) as span:
        try:
            yield span, status_holder
        except Exception:
            status_holder[0] = "error"
            raise
        finally:
            elapsed = time.monotonic() - start
            aegis_runs_total.labels(route=route, status=status_holder[0]).inc()
            aegis_run_duration_seconds.labels(route=route).observe(elapsed)
