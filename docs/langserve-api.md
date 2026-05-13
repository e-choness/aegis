# Phase 3: LangServe API Surface

## Overview

Phase 3 exposes the Aegis Gateway as a **LangServe-compatible API surface**, enabling seamless integration with LangChain applications and enabling remote execution of inference chains through HTTP.

All Phase 3 endpoints follow the [LangServe HTTP API specification](https://github.com/langchain-ai/langserve) for:
- Schema introspection
- Synchronous invocation (`/invoke`)
- Batch invocation (`/batch`)
- Streaming responses (`/stream`)

---

## Quick Start

### List Available Runnables

```bash
curl http://localhost:8000/api/v1/runnables
```

Response:
```json
{
  "runnables": [
    {
      "name": "inference",
      "description": "Execute an AI inference request with data classification, PII masking, and cost routing",
      "tags": ["inference", "classification", "pii_masking", "budget"],
      "input_schema": {...},
      "output_schema": {...}
    }
  ]
}
```

### Get Runnable Schema

```bash
curl http://localhost:8000/api/v1/runnables/inference/schema
```

Returns the input and output JSON schemas for code generation and validation.

### Invoke a Runnable

```bash
curl -X POST http://localhost:8000/api/v1/runnables/inference/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "Summarize this pull request",
      "task_type": "pr_review",
      "team_id": "platform",
      "user_id": "alice"
    },
    "config": {
      "metadata": {"trace_id": "abc-123"}
    }
  }'
```

Response:
```json
{
  "output": "The PR adds new user authentication...",
  "metadata": {
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "completed",
    "model_alias": "sonnet",
    "provider": "anthropic",
    "tier": 1,
    "cost_usd": 0.00234,
    "data_class": "INTERNAL"
  }
}
```

---

## API Endpoints

### `GET /api/v1/runnables`

List all available Runnables with metadata.

**Response `200 OK`**
```json
{
  "runnables": [
    {
      "name": "inference",
      "description": "Execute an AI inference request...",
      "tags": ["inference", "classification", "pii_masking", "budget"],
      "input_schema": {
        "type": "object",
        "properties": {
          "prompt": {"type": "string", "description": "..."},
          "task_type": {"type": "string", "description": "..."},
          "team_id": {"type": "string", "description": "..."},
          "user_id": {"type": "string", "description": "..."},
          "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
          "trace_id": {"type": "string", "description": "Optional trace ID"}
        },
        "required": ["prompt", "task_type", "team_id", "user_id"]
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "output": {"type": "string", "description": "LLM response text"},
          "metadata": {
            "type": "object",
            "properties": {
              "job_id": {"type": "string"},
              "status": {"type": "string"},
              "model_alias": {"type": "string"},
              "provider": {"type": "string"},
              "tier": {"type": "integer"},
              "cost_usd": {"type": "number"},
              "data_class": {"type": "string"}
            }
          }
        }
      }
    }
  ]
}
```

---

### `GET /api/v1/runnables/{name}/schema`

Get the input/output JSON schemas for a Runnable. Use this for client code generation and request validation.

**Path Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Runnable identifier (e.g., `inference`) |

**Response `200 OK`**
```json
{
  "name": "inference",
  "description": "Execute an AI inference request...",
  "tags": ["inference", "classification", "pii_masking", "budget"],
  "input_schema": {...},
  "output_schema": {...}
}
```

**Errors**
| Code | Reason |
|------|--------|
| `404` | Runnable `{name}` not found |

---

### `POST /api/v1/runnables/{name}/invoke`

Synchronously invoke a Runnable and wait for the result.

**Path Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Runnable identifier |

**Request Body**
```json
{
  "input": {
    "prompt": "Code review this pull request",
    "task_type": "pr_review",
    "team_id": "platform",
    "user_id": "alice",
    "complexity": "medium",
    "trace_id": "optional-trace-id"
  },
  "config": {
    "metadata": {
      "trace_id": "optional-correlation-id"
    }
  }
}
```

**Response `200 OK`**
```json
{
  "output": "The code changes look good. No issues detected.",
  "metadata": {
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "completed",
    "model_alias": "sonnet",
    "provider": "anthropic",
    "tier": 1,
    "cost_usd": 0.00234,
    "data_class": "INTERNAL",
    "latency_ms": 1240
  }
}
```

**Errors**
| Code | Reason |
|------|--------|
| `400` | Missing required fields (`prompt`, `team_id`, `user_id`) or invalid `task_type` |
| `404` | Runnable `{name}` not found |
| `429` | Team budget cap exceeded |
| `503` | All providers unavailable |

---

### `POST /api/v1/runnables/{name}/batch`

Invoke a Runnable with multiple inputs and return all results.

**Path Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Runnable identifier |

**Request Body**
```json
{
  "inputs": [
    {
      "prompt": "Summarize commit: ...",
      "task_type": "commit_summary",
      "team_id": "platform",
      "user_id": "alice"
    },
    {
      "prompt": "Review code: ...",
      "task_type": "pr_review",
      "team_id": "platform",
      "user_id": "bob"
    }
  ],
  "config": {
    "metadata": {"trace_id": "batch-123"}
  }
}
```

**Response `200 OK`**
```json
{
  "outputs": [
    {
      "output": "Added user authentication module...",
      "metadata": {
        "job_id": "job-001",
        "status": "completed",
        "cost_usd": 0.00012
      }
    },
    {
      "output": "Code looks good...",
      "metadata": {
        "job_id": "job-002",
        "status": "completed",
        "cost_usd": 0.00234
      }
    }
  ]
}
```

**Errors**
| Code | Reason |
|------|--------|
| `400` | Missing `inputs` field or empty array |
| `404` | Runnable `{name}` not found |

---

### `GET /api/v1/runnables/{name}/stream`

Stream a Runnable's output via Server-Sent Events (SSE).

**Path Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Runnable identifier |

**Query Parameters**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input_json` | string | Yes | JSON-encoded input object (URL-encoded) |

**Example**
```bash
INPUT='{"prompt":"Explain this code","task_type":"code_explanation","team_id":"team","user_id":"user"}'
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$INPUT'))")
curl "http://localhost:8000/api/v1/runnables/inference/stream?input_json=$ENCODED"
```

**Response `200 OK` (Server-Sent Events)**

```
event: token
data: {"token": "The", "metadata": {"job_id": "job-123", "status": "streaming", "model_alias": "sonnet"}}

event: token
data: {"token": " code", "metadata": {"job_id": "job-123"}}

event: token
data: {"token": " is", "metadata": {"job_id": "job-123"}}

event: done
data: {
  "output": "The code is well-structured...",
  "metadata": {
    "job_id": "job-123",
    "status": "completed",
    "cost_usd": 0.00156,
    "model_alias": "sonnet",
    "provider": "anthropic",
    "tier": 1
  }
}
```

**Stream Events**

| Event Type | Fields | Description |
|-----------|--------|-------------|
| `token` | `token` (string), `metadata` (object) | A single token from the LLM output |
| `done` | `output` (string), `metadata` (object) | Final response with complete metadata |
| `error` | `error` (string) | Error occurred during streaming |

**Errors**
| Code | Reason |
|------|--------|
| `400` | Missing or invalid `input_json` query parameter |
| `404` | Runnable `{name}` not found |

---

## Runnable: `inference`

The built-in `inference` Runnable executes AI inference with full Aegis governance:

- **Data Classification** — Automatically classifies input as RESTRICTED, CONFIDENTIAL, INTERNAL, or PUBLIC
- **PII Masking** — Detects and masks PII before sending to LLM
- **Cost Routing** — Selects optimal model (Haiku/Sonnet/Opus) based on task complexity and team budget
- **Budget Enforcement** — Checks team monthly cap before invoking
- **Audit Logging** — Records every invocation with team, user, cost, and model used
- **Provider Failover** — Automatic fallback from Anthropic → Azure OpenAI → Ollama

### Input Schema

```json
{
  "prompt": "string (required) — The prompt text",
  "task_type": "string (required) — Task for routing: commit_summary, pr_review, security_audit, etc.",
  "team_id": "string (required) — Team identifier for budget tracking",
  "user_id": "string (required) — User identifier for audit trail",
  "complexity": "string (optional, default=medium) — low | medium | high",
  "trace_id": "string (optional) — Correlation ID for tracing"
}
```

### Output Schema

```json
{
  "output": "string | null — LLM response text (null if failed)",
  "metadata": {
    "job_id": "string — Unique job identifier",
    "status": "completed | failed",
    "model_alias": "string — Model tier used (haiku, sonnet, opus)",
    "provider": "string — Provider used (anthropic, azure_openai, ollama)",
    "tier": "integer — Provider tier (1=cloud, 11=azure, 3=local)",
    "cost_usd": "number — Actual cost of this invocation",
    "data_class": "string — Classification applied (RESTRICTED, CONFIDENTIAL, INTERNAL, PUBLIC)",
    "error": "string | null — Error message if failed",
    "latency_ms": "integer — Response time in milliseconds"
  }
}
```

---

## Data Classifications

All inputs are automatically classified according to Aegis patterns:

| Classification | Triggers | Cloud Allowed | Inference Provider |
|---|---|---|---|
| `RESTRICTED` | Canadian SIN, credit card, account numbers | ❌ Never | Ollama (local only) |
| `CONFIDENTIAL` | API keys, bearer tokens, passwords | ✅ Yes | Ollama → Azure OpenAI |
| `INTERNAL` | Business data (default) | ✅ Yes | Anthropic → Azure → Ollama |
| `PUBLIC` | No sensitive patterns | ✅ Yes | Anthropic → Azure → Ollama |

### Example: RESTRICTED Data Routing

```bash
curl -X POST http://localhost:8000/api/v1/runnables/inference/invoke \
  -d '{
    "input": {
      "prompt": "My Canadian SIN is 123-456-789",
      "task_type": "general",
      "team_id": "hr",
      "user_id": "alice"
    }
  }'
```

Response will show `"tier": 3` and `"provider": "ollama"` (local-only routing enforced by code invariant).

---

## Task Types

Task type determines which model is selected:

| Task Type | Default Model | Examples |
|-----------|------|----------|
| `commit_summary` | Haiku | Summarize git commits |
| `simple_qa` | Haiku | Simple question answering |
| `pr_review` | Sonnet | Pull request code review |
| `security_audit` | Opus | Security vulnerability analysis |
| `architecture_review` | Opus | High-level design review |

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Human-readable error message",
  "type": "error_type",
  "status_code": 400
}
```

### Common Errors

**Missing required field**
```json
{
  "detail": "team_id and user_id are required",
  "status_code": 400
}
```

**Unknown Runnable**
```json
{
  "detail": "Runnable 'unknown' not found",
  "status_code": 404
}
```

**Budget exceeded**
```json
{
  "detail": "Team budget exceeded",
  "status_code": 429
}
```

---

## Observability

All Runnable invocations are:

1. **Audited** — Recorded in TimescaleDB with team, user, cost, model, provider
2. **Metered** — Tracked in Prometheus with labels for cost, latency, provider tier
3. **Traced** — Correlation IDs passed through via `trace_id` field

### Check Audit Log

```bash
# In database
SELECT team_id, model_alias, provider, cost_usd, created_at
FROM audit_log
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

### Check Metrics

```bash
curl http://localhost:9090/api/v1/query?query=gateway_requests_total
```

---

## Integration Examples

### Python with LangServe RemoteRunnable

```python
from langserve import RemoteRunnable

runnable = RemoteRunnable("http://localhost:8000/api/v1/runnables/inference")

result = runnable.invoke({
    "prompt": "Write a hello world function",
    "task_type": "code_explanation",
    "team_id": "platform",
    "user_id": "alice",
})

print(result["output"])
```

### TypeScript

```typescript
const response = await fetch("http://localhost:8000/api/v1/runnables/inference/invoke", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    input: {
      prompt: "Review this code",
      task_type: "pr_review",
      team_id: "platform",
      user_id: "alice",
    },
  }),
});

const result = await response.json();
console.log(result.output);
console.log(`Cost: $${result.metadata.cost_usd}`);
```

### Batch Processing

```python
results = runnable.batch([
    {"prompt": "P1", "task_type": "simple_qa", "team_id": "t1", "user_id": "u1"},
    {"prompt": "P2", "task_type": "simple_qa", "team_id": "t1", "user_id": "u2"},
    {"prompt": "P3", "task_type": "simple_qa", "team_id": "t1", "user_id": "u3"},
])

for r in results:
    print(f"Output: {r['output']}, Cost: ${r['metadata']['cost_usd']}")
```

### Streaming

```python
for event in runnable.stream({
    "prompt": "Explain quantum computing",
    "task_type": "code_explanation",
    "team_id": "platform",
    "user_id": "alice",
}):
    if "token" in event:
        print(event["token"], end="", flush=True)
```

---

## Testing

Run Phase 3 tests inside Docker:

```bash
# Run all LangServe tests
make test

# Run specific test file
docker-compose run --rm test pytest tests/test_langserve_runnables.py -v
docker-compose run --rm test pytest tests/test_langserve_streaming.py -v
docker-compose run --rm test pytest tests/test_langserve_e2e.py -v
```

---

## See Also

- [Architecture](architecture.md) — Design decisions and data flow
- [API Reference](api.md) — Phase 1/2 REST API
- [Development Guide](development.md) — How to extend Aegis
