"""Showcase page — DEP-3 thin server-rendered pipeline visualizer.

Serves a self-contained page that lets a user send a prompt and watch it
traverse the pipeline, surfacing verdict/event log, PII mask/unmask, and
the approval trigger.

Backend routes:
  GET  /showcase                    — serve the page
  POST /showcase/api/invoke         — run a prompt through the pipeline, return
                                      the full result (response, events, mask_map)
  GET  /showcase/api/runs           — recent run records from the run store
  POST /showcase/api/runs/{id}/resume — approve or deny a paused run (proxied)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_server.auth.protocol import Principal
from aegis_server.store.run_store import RunRecord, RunStore
from aegis_server.telemetry import run_span

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


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

_SHOWCASE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Aegis — Pipeline Showcase</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      margin: 0; padding: 0; color: #111; background: #fafafa;
    }
    header {
      background: #1a1a2e; color: #fff; padding: 18px 28px;
      display: flex; align-items: center; justify-content: space-between;
    }
    header h1 { font-size: 1.25rem; margin: 0; font-weight: 600; }
    header a { color: #a5b4fc; text-decoration: none; font-size: .9rem; }
    header a:hover { text-decoration: underline; }
    main { max-width: 1100px; margin: 28px auto; padding: 0 24px; }
    .panel {
      background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
      padding: 18px 20px; margin-bottom: 18px;
      box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }
    .panel h2 {
      margin: 0 0 10px; font-size: 1rem; color: #1f2937;
      display: flex; align-items: center; gap: 8px;
    }
    .badge {
      font-size: .7rem; font-weight: 600; text-transform: uppercase;
      letter-spacing: .08em; padding: 3px 8px; border-radius: 999px;
      background: #e0e7ff; color: #3730a3;
    }
    label { font-size: .85rem; color: #4b5563; display: block; margin-bottom: 6px; }
    textarea {
      width: 100%; min-height: 110px; padding: 10px 12px; border: 1px solid #d1d5db;
      border-radius: 8px; font: inherit; resize: vertical;
    }
    textarea:focus { outline: none; border-color: #6366f1; box-shadow: 0 0 0 3px #e0e7ff; }
    .row { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
    button {
      padding: 9px 16px; border: none; border-radius: 8px; cursor: pointer;
      font-weight: 600; font-size: .9rem; background: #4f46e5; color: #fff;
    }
    button:hover:not(:disabled) { background: #4338ca; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    button.secondary { background: #e5e7eb; color: #111; }
    button.secondary:hover:not(:disabled) { background: #d1d5db; }
    pre {
      background: #0f172a; color: #e2e8f0; padding: 14px 16px;
      border-radius: 8px; overflow: auto; font-size: .85rem; line-height: 1.45;
      white-space: pre-wrap; word-break: break-word;
    }
    .stage { margin: 6px 0 4px; font-size: .75rem; text-transform: uppercase; letter-spacing: .1em; color: #6366f1; font-weight: 700; }
    .verdict {
      display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: .8rem;
      font-weight: 700; margin-left: 6px;
    }
    .verdict.allow { background: #dcfce7; color: #166534; }
    .verdict.block { background: #fee2e2; color: #991b1b; }
    .verdict.sanitize { background: #fef9c3; color: #854d0e; }
    .verdict.require_approval { background: #e0e7ff; color: #3730a3; }
    .empty { color: #9ca3af; font-size: .9rem; padding: 16px 0; text-align: center; }
    table { width: 100%; border-collapse: collapse; font-size: .88rem; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }
    th { font-weight: 600; color: #374151; background: #f9fafb; font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; }
    code { font-size: .84em; background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 760px) { .split { grid-template-columns: 1fr; } }
    #msg { margin-top: 10px; padding: 10px 12px; border-radius: 8px; font-size: .9rem; display: none; }
    #msg.ok { background: #dcfce7; color: #166534; display: block; }
    #msg.err { background: #fee2e2; color: #991b1b; display: block; }
  </style>
</head>
<body>
  <header>
    <h1>Aegis — Pipeline Showcase</h1>
    <a href="/docs" target="_blank">OpenAPI docs &rarr;</a>
  </header>

  <main>
    <div class="panel">
      <h2>Prompt <span class="badge">mock provider</span></h2>
      <label for="prompt">Enter a prompt to traverse the governance pipeline</label>
      <textarea id="prompt" placeholder="Try: &quot;My email is user@example.com and my SSN is 123-45-6789&quot;">My email is user@example.com and my phone is 555-123-4567</textarea>
      <div class="row">
        <button id="sendBtn" onclick="sendPrompt()">Send prompt</button>
        <button class="secondary" onclick="refreshRuns()">Refresh runs</button>
        <span id="busy" style="font-size:.85rem;color:#6b7280;display:none;">Running…</span>
      </div>
      <div id="msg"></div>
    </div>

    <div class="split">
      <div class="panel">
        <h2>Verdict / Event log</h2>
        <div id="eventLog"><div class="empty">No events yet. Send a prompt to see pipeline verdicts.</div></div>
      </div>

      <div class="panel">
        <h2>PII mask / unmask</h2>
        <div id="piiPanel"><div class="empty">No PII detected.</div></div>
      </div>
    </div>

    <div class="panel">
      <h2>Recent runs</h2>
      <div id="runsTable"><div class="empty">Loading…</div></div>
    </div>

    <div class="panel">
      <h2>Approval queue <span class="badge">HITL</span></h2>
      <div id="approvalPanel"><div class="empty">Loading…</div></div>
    </div>
  </main>

  <script>
    const BASE = window.location.origin;

    function esc(s) {
      try { s = String(s); } catch { return ""; }
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function flash(id, text, ok) {
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = ok ? 'ok' : 'err';
      setTimeout(() => { el.className = ''; el.textContent = ''; }, 6000);
    }

    function verdictClass(v) {
      const map = { allow: 'allow', block: 'block', sanitize: 'sanitize', require_approval: 'require_approval' };
      return map[v] || 'allow';
    }

    function renderEvents(events) {
      const el = document.getElementById('eventLog');
      if (!events || !events.length) { el.innerHTML = '<div class="empty">No events.</div>'; return; }
      el.innerHTML = events.map(ev => {
        const stage = esc(ev.stage || '');
        const node = esc(ev.node || '');
        const etype = esc(ev.event_type || '');
        const data = ev.data || {};
        const v = data.verdict ? data.verdict.toLowerCase() : '';
        const verdict = data.verdict ? `<span class="verdict ${verdictClass(v)}">${esc(data.verdict)}</span>` : '';
        let extra = '';
        if (data.reason) extra += `<div style="font-size:.8rem;color:#4b5563;margin-top:3px;">Reason: ${esc(String(data.reason))}</div>`;
        if (data.detail) extra += `<div style="font-size:.8rem;color:#4b5563;margin-top:3px;">Detail: ${esc(String(data.detail))}</div>`;
        if (data.run_id) extra += `<div style="font-size:.8rem;color:#9ca3af;margin-top:3px;">run_id: <code>${esc(data.run_id)}</code></div>`;
        return `<div>
          <div class="stage">${stage} / ${node} — ${etype} ${verdict}</div>
          <pre>${extra || '&nbsp;'}</pre>
        </div>`;
      }).join('');
    }

    function renderPii(maskMap, response) {
      const el = document.getElementById('piiPanel');
      if (!maskMap || Object.keys(maskMap).length === 0) {
        el.innerHTML = '<div class="empty">No PII detected.</div>';
        return;
      }
      const pairs = Object.entries(maskMap).map(([placeholder, original]) => {
        return `<tr>
          <td><code>${esc(placeholder)}</code></td>
          <td>${esc(original)}</td>
        </tr>`;
      }).join('');
      const respBlock = response
        ? `<div style="margin-top:10px;"><strong>Response (masked provider view):</strong><pre>${esc(response)}</pre></div>`
        : '';
      el.innerHTML = `<table>
        <thead><tr><th>Placeholder</th><th>Original value</th></tr></thead>
        <tbody>${pairs}</tbody>
      </table>${respBlock}`;
    }

    async function sendPrompt() {
      const btn = document.getElementById('sendBtn');
      const busy = document.getElementById('busy');
      const promptEl = document.getElementById('prompt');
      btn.disabled = true;
      busy.style.display = 'inline';
      try {
        const r = await fetch(`${BASE}/showcase/api/invoke`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: promptEl.value, route: 'default' }),
        });
        const data = await r.json();
        if (!r.ok) {
          flash('msg', String(data.detail || data), false);
          return;
        }
        renderEvents(data.events || []);
        renderPii(data.mask_map || {}, data.response);
        if (data.status === 'require_approval') {
          flash('msg', 'Run paused — approval required.', true);
        } else {
          flash('msg', `Run completed (${data.status}).`, true);
        }
      } catch (e) {
        flash('msg', 'Request failed: ' + (e.message || e), false);
      } finally {
        btn.disabled = false;
        busy.style.display = 'none';
        refreshRuns();
      }
    }

    async function refreshRuns() {
      const el = document.getElementById('runsTable');
      try {
        const r = await fetch(`${BASE}/showcase/api/runs`);
        const data = await r.json();
        const runs = (data.runs || []).slice(0, 20);
        if (!runs.length) { el.innerHTML = '<div class="empty">No runs yet.</div>'; return; }
        el.innerHTML = `<table>
          <thead><tr><th>Run ID</th><th>Route</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>${runs.map(run => `<tr>
            <td><code title="${esc(run.run_id)}">${esc(run.run_id.slice(0,8))}\u2026</code></td>
            <td>${esc(run.route)}</td>
            <td><span class="verdict ${verdictClass(run.status)}">${esc(run.status)}</span></td>
            <td style="white-space:nowrap;color:#4b5563;">${esc(run.created_at ? run.created_at.replace('T',' ').slice(0,19) : '—')}</td>
          </tr>`).join('')}</tbody>
        </table>`;
      } catch {
        el.innerHTML = '<div class="empty">Failed to load runs.</div>';
      }
    }

    async function refreshApprovals() {
      const el = document.getElementById('approvalPanel');
      try {
        const r = await fetch(`${BASE}/showcase/api/runs`);
        const data = await r.json();
        const paused = (data.runs || []).filter(run => run.status === 'paused');
        if (!paused.length) {
          el.innerHTML = '<div class="empty">No pending approvals.</div>';
          return;
        }
        el.innerHTML = `<table>
          <thead><tr><th>Run ID</th><th>Route</th><th>Created</th><th>Actions</th></tr></thead>
          <tbody>${paused.map(run => `<tr id="row-${run.run_id}">
            <td><code title="${esc(run.run_id)}">${esc(run.run_id.slice(0,8))}\u2026</code></td>
            <td>${esc(run.route)}</td>
            <td style="white-space:nowrap;color:#4b5563;">${esc(run.created_at ? run.created_at.replace('T',' ').slice(0,19) : '—')}</td>
            <td>
              <button onclick="resumeRun('${run.run_id}','approved')">Approve</button>
              <button class="secondary" onclick="resumeRun('${run.run_id}','denied')">Deny</button>
            </td>
          </tr>`).join('')}</tbody>
        </table>`;
      } catch {
        el.innerHTML = '<div class="empty">Failed to load approvals.</div>';
      }
    }

    async function resumeRun(runId, decision) {
      try {
        const r = await fetch(`${BASE}/showcase/api/runs/${runId}/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision }),
        });
        const data = await r.json();
        if (!r.ok) {
          flash('msg', String(data.detail || data), false);
          return;
        }
        flash('msg', `Run ${runId.slice(0,8)}\u2026 ${decision}.`, true);
        refreshApprovals();
        refreshRuns();
      } catch (e) {
        flash('msg', 'Request failed: ' + (e.message || e), false);
      }
    }

    refreshRuns();
    refreshApprovals();
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@router.get("/showcase", response_class=HTMLResponse, include_in_schema=False)
async def showcase_page() -> str:
    return _SHOWCASE_HTML


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

@router.post("/showcase/api/invoke", response_model=InvokeResponse)
async def invoke_prompt(body: InvokeRequest, request: Request) -> InvokeResponse:
    executor: PipelineExecutor = request.app.state.executor  # type: ignore[attr-defined]
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    principal: Principal = request.state.principal  # type: ignore[attr-defined]

    try:
        pipeline = executor.get(body.route)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No pipeline for route '{body.route}'") from exc

    messages = [Message(role="user", content=body.prompt)]
    run_id = str(uuid.uuid4())
    state = RunState(
        run_id=run_id,
        route=body.route,
        messages=messages,
        principal=principal.id,
    )

    record = RunRecord(
        run_id=run_id,
        route=body.route,
        principal_id=principal.id,
        status="running",
    )
    await run_store.create(record)

    tracer = getattr(request.app.state, "tracer", None)
    async with run_span(body.route, run_id, principal.id, tracer=tracer) as (span, status_holder):
        result = await pipeline.run(state)
        span.set_attribute("run.status", result.status)
        status_holder[0] = result.status

    await run_store.update_status(run_id, result.status)

    return InvokeResponse(
        run_id=result.run_id,
        response=result.response,
        status=result.status,
        events=[e.to_dict() for e in result.events],
        mask_map=result.mask_map or {},
    )


@router.get("/showcase/api/runs")
async def showcase_list_runs(request: Request) -> dict[str, list[dict[str, object]]]:
    run_store: RunStore = request.app.state.run_store  # type: ignore[attr-defined]
    records = await run_store.list_runs()
    return {"runs": [r.to_dict() for r in records]}


@router.post("/showcase/api/runs/{run_id}/resume")
async def showcase_resume_run(run_id: str, body: dict[str, str], request: Request) -> dict[str, object]:
    from aegis_server.routes.hitl import resume_run as _hitl_resume, ResumeRequest
    req = ResumeRequest(decision=body.get("decision", "approved"))
    result = await _hitl_resume(run_id, req, request)
    return result.model_dump()
