# REST API

Base URL: wherever `aegis serve` listens (default `http://localhost:8000`).
The machine-readable spec is
[`openapi.json`](https://github.com/e-choness/aegis/blob/main/openapi.json);
generate a client for any language from it with openapi-generator
(`docker compose --profile codegen run --rm codegen generate -i /workspace/openapi.json -g go -o /workspace/.tmp/go`).

## Authentication

Every endpoint except `/metrics` requires

```text
Authorization: Bearer aeg-<64 hex>
```

unless the server runs with `--no-auth`. A missing or unknown key returns:

```json
{"code": "AEG-AUTH-001", "detail": "AEG-AUTH-001: unauthorized — no valid credential. ..."}
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat (streaming and non-streaming) |
| `GET` | `/v1/models` | OpenAI-compatible model list — one entry per route |
| `POST` | `/v1/runs` | Create a governed run (sync or background) |
| `GET` | `/v1/runs/{run_id}` | Run status and events |
| `POST` | `/v1/runs/{run_id}/resume` | Approve or deny a paused run |
| `GET` | `/v1/audit` | Query runs by principal, route, time |
| `GET` | `/v1/audit/ledger` | Hash-chained ledger records |
| `GET` | `/v1/audit/inventory` | `model_inventory` records |
| `GET` | `/v1/audit/report` | Inventory, run counts by status, chain length |
| `POST` | `/v1/rag/index` | Index documents (503 unless RAG is configured) |
| `POST` | `/v1/rag/query` | Query the vector store (503 unless RAG is configured) |
| `GET` | `/v1/health` | Liveness + config digest |
| `GET` | `/metrics` | Prometheus metrics (no auth) |
| `GET` | `/approvals` | HTML page for reviewing paused runs |
| `GET` | `/showcase` | Interactive demo page (`/` redirects here) |

## `POST /v1/chat/completions`

Drop-in for OpenAI's chat completions. **`model` is the Aegis route name.**

```json
{
  "model": "default",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}
```

Response: the standard `chat.completion` object (`id`, `object`, `created`,
`model`, `choices[].message`, `choices[].finish_reason`, `usage`).
`finish_reason` is `content_filter` when the run was blocked, paused or
denied — look the run up with `aegis explain --last` or `GET /v1/audit`.
Every chat request is recorded as a run, streamed or not.

With `"stream": true` the response is `text/event-stream` of
`chat.completion.chunk` frames ending in `data: [DONE]`. A guard violation
ends the stream with `finish_reason: "content_filter"` and an extra
`aegis_event` field (`stream_violation` or `late_violation`). If ingress
stops the request, the stream is a single frame with `aegis_event` set to
`blocked`, `paused` or `denied` plus `aegis_run_id`. See
[Streaming](/guide/streaming).

## `GET /v1/models`

```json
{"object": "list", "data": [{"id": "default", "object": "model", "created": 0, "owned_by": "aegis"}]}
```

Lets OpenAI-compatible UIs (Open WebUI, LibreChat, …) discover the routes.

## `POST /v1/runs`

```json
{
  "route": "default",
  "messages": [{"role": "user", "content": "Hello"}],
  "approvers": ["jane"],
  "background": false
}
```

| Field | Default | Notes |
|---|---|---|
| `route` | `"default"` | Unknown route → 404. |
| `messages` | — | `[{role, content}]` |
| `approvers` | `[]` | Principal ids allowed to resume if the run pauses. Empty = anyone authenticated. |
| `background` | `false` | Return immediately with `status: "pending"`; poll `GET /v1/runs/{id}`. |

Response:

```json
{
  "run_id": "3f0c…",
  "status": "completed",
  "response": "…",
  "principal_id": "alice",
  "events": [{"stage": "guard", "node": "pii", "event_type": "verdict", "data": {"verdict": "allow"}}]
}
```

`status` is one of `completed`, `blocked`, `paused`, `denied`, `pending`,
`running`, `error`.

## `GET /v1/runs/{run_id}`

```json
{
  "run_id": "3f0c…",
  "route": "default",
  "principal_id": "alice",
  "status": "paused",
  "approvers": ["jane"],
  "events": [],
  "config_digest": "sha256:…"
}
```

## `POST /v1/runs/{run_id}/resume`

```json
{"decision": "approved"}
```

`decision` is `approved` or `denied`. Returns `{run_id, status, response, events}`.
**403** `AEG-AUTH-003` if the caller isn't an approver; **409** if the run
isn't paused; **404** if unknown.

## `GET /v1/audit`

Query parameters (all optional, ANDed): `principal`, `route`, `since`
(ISO-8601 lower bound on `created_at`). Returns `{"runs": [...]}` from the
run store.

## Ledger endpoints

| Endpoint | Query | Returns |
|---|---|---|
| `/v1/audit/ledger` | `since_seq` (default 0), `route` | `{"records": [...]}` in sequence order |
| `/v1/audit/inventory` | `route` | `{"records": [...]}` — `model_inventory` only |
| `/v1/audit/report` | — | `{generated_at, inventory, run_stats, chain_length}` |

Record fields are described in [Audit & evidence ledger](/guide/audit).

## RAG endpoints

```jsonc
// POST /v1/rag/index
{"namespace": "hr", "documents": [{"text": "…", "metadata": {"source": "handbook.md"}}]}
// → {"indexed": 1, "namespace": "hr"}

// POST /v1/rag/query
{"namespace": "hr", "query": "vacation policy", "k": 4}
// → {"namespace": "hr", "docs": [{"id": "…", "text": "…", "metadata": {}}]}
```

## `GET /v1/health`

```json
{"status": "ok", "config_digest": "sha256:…", "config_path": "/etc/aegis/aegis.yaml"}
```
