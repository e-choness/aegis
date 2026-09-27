"""Showcase page — DEP-3 thin server-rendered pipeline visualizer.

Public-demo safety rails (`aegis serve --demo`): per-visitor rate limit + rolling cap.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict, deque
from importlib.resources import files
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_server.auth.protocol import Principal
from aegis_server.recording import record_run
from aegis_server.store.run_store import RunRecord, RunStore
from aegis_server.telemetry import run_span

# ---------------------------------------------------------------------------
# Demo safety rails (`aegis serve --demo`)
# ---------------------------------------------------------------------------

_RATE_LIMIT: int = 10  # pipeline runs (POSTs) per visitor per minute
_HOURLY_CAP: int = 600  # pipeline runs across all visitors per rolling hour
_UNLIMITED_PATHS: tuple[str, ...] = ("/v1/health",)


def _client_ip(scope: Scope) -> str:
    """The visitor's address — the first X-Forwarded-For hop when behind a proxy.

    Public demos (e.g. Hugging Face Spaces) sit behind a proxy, so the socket
    peer is the proxy itself; without this every visitor would share one quota.
    """
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            first = value.decode("latin-1").split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    return client[0] if client else "unknown"


class DemoRateLimitMiddleware:
    """Per-visitor rate limit plus a rolling global cap, for public demos.

    Only requests that do work are limited — non-GET calls to ``/v1/*`` and
    ``/showcase/api/*`` (running a prompt, creating or resuming a run).  Reads,
    pages and ``/v1/health`` are free, so the showcase page's own polling
    doesn't eat a visitor's quota.  State lives on the instance,
    so separate apps (and tests) don't share quotas.  The client address is
    taken from ``X-Forwarded-For`` — only enable this behind a proxy you trust.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int = _RATE_LIMIT,
        per_hour: int = _HOURLY_CAP,
    ) -> None:
        self._app = app
        self._per_minute = per_minute
        self._per_hour = per_hour
        self._by_ip: dict[str, deque[float]] = defaultdict(deque)
        self._all: deque[float] = deque()

    @staticmethod
    def _limited(method: str, path: str) -> bool:
        if method in ("GET", "HEAD", "OPTIONS") or path in _UNLIMITED_PATHS:
            return False
        return path.startswith(("/v1/", "/showcase/api/"))

    @staticmethod
    def _prune(window: deque[float], now: float, seconds: float) -> None:
        while window and now - window[0] >= seconds:
            window.popleft()

    async def _reject(self, scope: Scope, receive: Receive, send: Send, detail: str) -> None:
        response = JSONResponse({"detail": detail}, status_code=429, headers={"Retry-After": "60"})
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._limited(
            scope.get("method", "GET"), scope.get("path", "")
        ):
            await self._app(scope, receive, send)
            return

        now = time.monotonic()
        self._prune(self._all, now, 3600)
        if len(self._all) >= self._per_hour:
            await self._reject(scope, receive, send, "Demo is busy — please try again later.")
            return

        ip = _client_ip(scope)
        mine = self._by_ip[ip]
        self._prune(mine, now, 60)
        if len(mine) >= self._per_minute:
            await self._reject(scope, receive, send, "Rate limit exceeded. Please wait a moment.")
            return

        mine.append(now)
        self._all.append(now)
        if len(self._by_ip) > 10_000:  # forget idle visitors
            for key in [k for k, v in self._by_ip.items() if not v]:
                del self._by_ip[key]
        await self._app(scope, receive, send)


router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    prompt: str
    route: str = "default"


class InvokeResponse(BaseModel):
    run_id: str
    response: str | None
    status: str
    events: list[dict[str, Any]]
    mask_map: dict[str, str]
    labels: dict[str, str] = {}
    cost: float = 0.0


# The page lives next to the code (aegis_server/static/showcase.html) so it can
# be edited as HTML; it reads everything it shows from the endpoints below.
_SHOWCASE_HTML = files("aegis_server").joinpath("static/showcase.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _visitor_principal(principal_id: str, request: Request) -> str:
    """In demo mode, give each anonymous visitor their own principal.

    Budgets and runs are per principal; without this every visitor of a public
    demo would share — and exhaust — one budget. The address is hashed, never
    stored.
    """
    if principal_id != "anonymous" or not getattr(request.app.state, "demo_mode", False):
        return principal_id
    digest = hashlib.sha256(_client_ip(request.scope).encode()).hexdigest()[:10]
    return f"visitor-{digest}"


@router.get("/showcase", response_class=HTMLResponse, include_in_schema=False)
async def showcase_page() -> str:
    return _SHOWCASE_HTML


@router.get("/showcase/api/tabs", include_in_schema=False)
async def showcase_tabs(request: Request) -> dict[str, list[dict[str, Any]]]:
    """The scenario tabs: built from the config by ``aegis serve``, or one per route."""
    tabs = getattr(request.app.state, "showcase_tabs", None)
    if tabs:
        return {"tabs": tabs}
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    return {
        "tabs": [
            {
                "id": route,
                "title": route,
                "order": 100,
                "blurb": "",
                "routes": [{"route": route, "label": route, "presets": [], "config": ""}],
            }
            for route in executor.routes()
        ]
    }


@router.post("/showcase/api/invoke", response_model=InvokeResponse, include_in_schema=False)
async def invoke_prompt(body: InvokeRequest, request: Request) -> InvokeResponse:
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]
    principal_id = _visitor_principal(principal.id, request)

    try:
        pipeline = executor.get(body.route)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"No pipeline for route '{body.route}'"
        ) from exc

    run_id = str(uuid.uuid4())
    state = RunState(
        run_id=run_id,
        route=body.route,
        messages=[Message(role="user", content=body.prompt)],
        principal=principal_id,
    )
    record = RunRecord(run_id=run_id, route=body.route, principal_id=principal_id, status="running")
    await run_store.create(record)

    tracer = getattr(request.app.state, "tracer", None)
    async with run_span(body.route, run_id, principal_id, tracer=tracer) as (span, status_holder):
        result = await pipeline.run(state)
        span.set_attribute("run.status", result.status)
        status_holder[0] = result.status

    events = [e.to_dict() for e in result.events]
    # Same audit trail as /v1/runs: the Audit tab explains and verifies these runs.
    await record_run(
        run_store=run_store,
        ledger_store=getattr(request.app.state, "ledger_store", None),
        run_id=run_id,
        route=body.route,
        principal_id=principal_id,
        created_at=record.created_at,
        config_digest=getattr(request.app.state, "config_digest", None),
        status=result.status,
        events=events,
    )

    return InvokeResponse(
        run_id=result.run_id,
        response=result.response,
        status=result.status,
        events=events,
        mask_map=result.mask_map or {},
        labels=result.labels or {},
        cost=result.usage.cost if result.usage else 0.0,
    )


@router.get("/showcase/api/runs", include_in_schema=False)
async def showcase_list_runs(request: Request) -> dict[str, list[dict[str, object]]]:
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    records = await run_store.list_runs()
    # Newest first: the page shows the latest 20, which must include the run just made.
    records.sort(key=lambda r: r.created_at, reverse=True)
    return {"runs": [r.to_dict() for r in records]}


@router.post("/showcase/api/runs/{run_id}/resume", include_in_schema=False)
async def showcase_resume_run(
    run_id: str, body: dict[str, str], request: Request
) -> dict[str, object]:
    from aegis_server.routes.hitl import ResumeRequest, resume_run as _hitl_resume  # noqa: I001

    req = ResumeRequest(decision=body.get("decision", "approved"))
    result = await _hitl_resume(run_id, req, request)
    return result.model_dump()
