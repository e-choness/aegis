"""GET /approvals — minimal HITL approval UI (static HTML over the runs API).

Serves a self-contained page that lists paused runs and lets reviewers
approve or deny them via the /v1/runs/{id}/resume endpoint.

≤ 200 lines total (PROJECT_SPEC step 17).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_APPROVALS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Aegis — Pending Approvals</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 48px auto; padding: 0 24px; color: #111; }
    h1 { font-size: 1.6rem; color: #1a1a2e; margin-bottom: 4px; }
    p.sub { color: #555; font-size: .9rem; margin-top: 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th, td { padding: 10px 14px; border-bottom: 1px solid #e0e0e0; text-align: left; }
    th { background: #f8f8f8; font-weight: 600; font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; }
    td code { font-size: .85em; background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
    .btn { padding: 5px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: .85rem; font-weight: 500; }
    .approve { background: #22c55e; color: #fff; }
    .approve:hover { background: #16a34a; }
    .deny { background: #ef4444; color: #fff; margin-left: 6px; }
    .deny:hover { background: #dc2626; }
    #msg { margin-top: 16px; padding: 10px 14px; border-radius: 6px; display: none; font-size: .9rem; }
    .ok  { background: #dcfce7; color: #166534; }
    .err { background: #fee2e2; color: #991b1b; }
    .empty { color: #888; padding: 20px 0; text-align: center; }
  </style>
</head>
<body>
  <h1>Aegis &mdash; Pending Approvals</h1>
  <p class="sub">Runs with status <strong>paused</strong>. Auto-refreshes every 5 s.</p>
  <div id="msg"></div>
  <table>
    <thead>
      <tr>
        <th>Run ID</th><th>Route</th><th>Principal</th><th>Created</th><th>Actions</th>
      </tr>
    </thead>
    <tbody id="tbody"><tr><td colspan="5" class="empty">Loading&hellip;</td></tr></tbody>
  </table>

  <script>
    const BASE = window.location.origin;

    async function load() {
      let data;
      try {
        const r = await fetch(BASE + '/v1/audit');
        data = await r.json();
      } catch (e) {
        flash('Failed to reach API: ' + e.message, false);
        return;
      }
      const runs = (data.runs || []).filter(r => r.status === 'paused');
      const tb = document.getElementById('tbody');
      if (!runs.length) {
        tb.innerHTML = '<tr><td colspan="5" class="empty">No pending approvals.</td></tr>';
        return;
      }
      tb.innerHTML = runs.map(run => {
        const short = run.run_id.slice(0, 8) + '\u2026';
        const ts = run.created_at ? run.created_at.replace('T', ' ').slice(0, 19) + ' UTC' : '—';
        return `<tr id="row-${run.run_id}">
          <td><code title="${run.run_id}">${short}</code></td>
          <td>${esc(run.route)}</td>
          <td>${esc(run.principal_id)}</td>
          <td style="font-size:.82rem;color:#555">${ts}</td>
          <td>
            <button class="btn approve" onclick="decide('${run.run_id}','approved')">Approve</button>
            <button class="btn deny"    onclick="decide('${run.run_id}','denied')">Deny</button>
          </td>
        </tr>`;
      }).join('');
    }

    async function decide(runId, decision) {
      try {
        const r = await fetch(`${BASE}/v1/runs/${runId}/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: r.statusText }));
          const msg = typeof err.detail === 'object' ? (err.detail.detail || JSON.stringify(err.detail)) : err.detail;
          throw new Error(msg);
        }
        flash(`Run ${runId.slice(0,8)}\u2026 ${decision}.`, true);
        document.getElementById('row-' + runId)?.remove();
        if (!document.getElementById('tbody').querySelector('tr[id]')) {
          document.getElementById('tbody').innerHTML =
            '<tr><td colspan="5" class="empty">No pending approvals.</td></tr>';
        }
      } catch (e) {
        flash(e.message, false);
      }
    }

    function flash(msg, ok) {
      const el = document.getElementById('msg');
      el.textContent = msg;
      el.className = ok ? 'ok' : 'err';
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 5000);
    }

    function esc(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    load();
    setInterval(load, 5000);
  </script>
</body>
</html>
"""


@router.get("/approvals", response_class=HTMLResponse, include_in_schema=False)
async def approvals_page() -> str:
    """Serve the minimal HITL approvals page."""
    return _APPROVALS_HTML
