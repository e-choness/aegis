"""Aegis server app factory (PROJECT_SPEC D9, D17)."""

from __future__ import annotations

from fastapi import FastAPI

from aegis_server.auth import NoneAuthenticator
from aegis_server.middleware import AuthMiddleware
from aegis_server.routes.chat import router as chat_router
from aegis_server.routes.runs import router as runs_router


class AEGServError(RuntimeError):
    """AEG-SRV-001: serve refused without an authenticator and without --no-auth."""


def create_app(
    executor: object,
    authenticator: object | None = None,
    *,
    no_auth: bool = False,
) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    executor:
        A :class:`~aegis_core.pipeline.executor.PipelineExecutor`.
    authenticator:
        An :class:`~aegis_server.auth.Authenticator` implementation.
        Required unless *no_auth* is ``True``.
    no_auth:
        If ``True`` use :class:`~aegis_server.auth.NoneAuthenticator` (dev mode).

    Raises
    ------
    AEGServError
        AEG-SRV-001 — if *authenticator* is ``None`` and *no_auth* is ``False``.
    """
    if authenticator is None and not no_auth:
        raise AEGServError(
            "AEG-SRV-001: serve refused — no authenticator configured. "
            "Pass --no-auth or configure an authenticator."
        )
    if no_auth:
        authenticator = NoneAuthenticator()

    app = FastAPI(title="Aegis AI Gateway", version="2.0.0a0")
    app.state.executor = executor
    app.add_middleware(AuthMiddleware, authenticator=authenticator)
    app.include_router(runs_router)
    app.include_router(chat_router)
    return app
