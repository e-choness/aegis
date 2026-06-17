"""Aegis server app factory (PROJECT_SPEC D9, D17)."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace

from aegis_server.auth import NoneAuthenticator
from aegis_server.middleware import AuthMiddleware
from aegis_server.routes.showcase import router as showcase_router
from aegis_server.routes.approvals import router as approvals_router
from aegis_server.routes.audit import router as audit_router
from aegis_server.routes.chat import router as chat_router
from aegis_server.routes.hitl import router as hitl_router
from aegis_server.routes.rag import router as rag_router
from aegis_server.routes.runs import router as runs_router
from aegis_server.store.run_store import InMemoryRunStore
from aegis_server.telemetry import make_metrics_app


class AEGServError(RuntimeError):
    """AEG-SRV-001: serve refused without an authenticator and without --no-auth."""


def create_app(
    executor: object,
    authenticator: object | None = None,
    *,
    run_store: object | None = None,
    rag_store: object | None = None,
    embedding_provider: object | None = None,
    no_auth: bool = False,
    tracer: trace.Tracer | None = None,
) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    executor:
        A :class:`~aegis_core.pipeline.executor.PipelineExecutor`.
    authenticator:
        An :class:`~aegis_server.auth.Authenticator` implementation.
        Required unless *no_auth* is ``True``.
    run_store:
        A :class:`~aegis_server.store.RunStore` implementation.
        Defaults to :class:`~aegis_server.store.InMemoryRunStore` when ``None``.
    rag_store:
        A :class:`~aegis_core.rag.VectorStoreProvider` implementation.
        When ``None`` the ``/v1/rag/*`` endpoints return 503.
    embedding_provider:
        An :class:`~aegis_core.rag.EmbeddingProvider` implementation.
        Required when *rag_store* is set.
    no_auth:
        If ``True`` use :class:`~aegis_server.auth.NoneAuthenticator` (dev mode).

    Raises
    ------
    AEGServError
        AEG-SRV-001 — if *authenticator* is ``None`` and *no_auth* is ``False``.
    """
    if authenticator is None and not no_auth:
        raise AEGServError(
            "AEG-SRV-001: serve refused - no authenticator configured. "
            "Pass --no-auth or configure an authenticator."
        )
    if no_auth:
        authenticator = NoneAuthenticator()

    app = FastAPI(title="Aegis AI Gateway", version="2.0.0a0")
    app.state.executor = executor
    app.state.run_store = run_store if run_store is not None else InMemoryRunStore()
    app.state.rag_store = rag_store
    app.state.embedding_provider = embedding_provider
    app.state.tracer = tracer  # None -> runs.py falls back to global OTel tracer
    app.add_middleware(AuthMiddleware, authenticator=authenticator)
    app.include_router(showcase_router)
    app.include_router(runs_router)
    app.include_router(chat_router)
    app.include_router(hitl_router)
    app.include_router(rag_router)
    app.include_router(audit_router)
    app.include_router(approvals_router)

    # Mount Prometheus /metrics endpoint (unauthenticated - Prometheus scrapes it)
    app.mount("/metrics", make_metrics_app())

    return app
