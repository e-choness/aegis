# REST API reference

Aegis exposes two API families:

- **Native API** — `/v1/runs`, `/v1/audit`, `/v1/runs/{id}/resume` etc.
- **OpenAI-compatible API** — `/v1/chat/completions` (drop-in for any OpenAI client)

The interactive spec below is generated from the live FastAPI application.

<swagger-ui src="../assets/openapi.json"/>

## Authentication

All endpoints except `/metrics` require a bearer token:

```
Authorization: Bearer aeg-<64-hex-chars>
```

Create keys with `aegis keys create`. The `dev` server (`aegis dev`) runs
without auth.

## Native endpoints

### `POST /v1/runs`

Create and execute a governed run.

**Request:**

```json
{
  "messages": [{"role": "user", "content": "Hello"}],
  "route": "default",
  "background": false,
  "approvers": []
}
```

**Response:**

```json
{
  "run_id": "550e8400-...",
  "status": "completed",
  "response": "...",
  "usage": {"prompt_tokens": 10, "completion_tokens": 25, "total_tokens": 35}
}
```

Status values: `pending`, `running`, `completed`, `paused`, `blocked`, `error`

### `GET /v1/runs/{run_id}`

Poll the status of a run.

### `POST /v1/runs/{run_id}/resume`

Resume a paused run. Requires the caller's principal to be in the run's
`approvers` list.

```json
{"decision": "approved"}
```

### `GET /v1/audit`

Retrieve run audit records with optional filters.

Query parameters: `principal`, `route`, `since` (ISO-8601)

### `POST /v1/rag/index`

Index documents into the vector store.

### `POST /v1/rag/query`

Query the vector store (returns governed context).

## OpenAI-compatible endpoint

### `POST /v1/chat/completions`

Drop-in replacement for the OpenAI chat completions API. All standard
OpenAI clients work without modification — just change `base_url`.

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="any-aegis-key",
)
response = client.chat.completions.create(
    model="default",  # maps to the "default" Aegis route
    messages=[{"role": "user", "content": "Hello!"}],
)
```

Streaming (`stream=True`) is fully supported — the response uses standard
OpenAI SSE wire format.

## Error format

All errors follow the `AEG-<AREA>-<NNN>` code format:

```json
{
  "error": {
    "code": "AEG-AUTH-001",
    "what": "Invalid or missing API key",
    "why": "Bearer token did not match any active key",
    "fix": "Create a key with `aegis keys create` and pass it as Bearer"
  }
}
```

See [error codes](errors.md) for the full table.
