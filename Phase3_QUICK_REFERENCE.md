# Phase 3 LangServe API - Quick Reference

## Files Created

### Core Implementation
- `src/aegis/api/v1/langserve.py` — LangServe endpoints (invoke, batch, stream, schema, list)
- `src/aegis/services/runnable_factory.py` — Runnable factory and schemas
- `src/aegis/main.py` — Integration (updated)

### Tests
- `tests/test_langserve_runnables.py` — Unit tests (30+ tests)
- `tests/test_langserve_streaming.py` — Integration tests (30+ tests)
- `tests/test_langserve_e2e.py` — E2E tests (20+ tests)

### Documentation
- `docs/langserve-api.md` — API reference with examples
- `docs/langserve-integration.md` — Integration guide (Python, TypeScript, cURL)
- `docs/PHASE3_IMPLEMENTATION_SUMMARY.md` — This implementation summary

---

## Quick Start

### Run Tests in Docker

```bash
# All Phase 3 LangServe tests
make test

# Specific test suite
docker-compose run --rm test pytest tests/test_langserve_runnables.py -v
docker-compose run --rm test pytest tests/test_langserve_streaming.py -v
docker-compose run --rm test pytest tests/test_langserve_e2e.py -v

# With coverage
docker-compose run --rm test pytest --cov=src tests/test_langserve_*.py
```

### Test the API Manually

```bash
# List Runnables
curl http://localhost:8000/api/v1/runnables | jq

# Get schema
curl http://localhost:8000/api/v1/runnables/inference/schema | jq

# Invoke
curl -X POST http://localhost:8000/api/v1/runnables/inference/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "prompt": "Hello world",
      "task_type": "simple_qa",
      "team_id": "platform",
      "user_id": "alice"
    },
    "config": {}
  }' | jq

# Batch
curl -X POST http://localhost:8000/api/v1/runnables/inference/batch \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [
      {"prompt": "P1", "task_type": "simple_qa", "team_id": "t1", "user_id": "u1"},
      {"prompt": "P2", "task_type": "simple_qa", "team_id": "t1", "user_id": "u2"}
    ],
    "config": {}
  }' | jq

# Stream
INPUT='{"prompt":"Hello","task_type":"simple_qa","team_id":"t1","user_id":"u1"}'
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$INPUT'))")
curl "http://localhost:8000/api/v1/runnables/inference/stream?input_json=$ENCODED"
```

---

## LangServe API Overview

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/runnables` | List all Runnables |
| GET | `/api/v1/runnables/{name}/schema` | Get input/output schema |
| POST | `/api/v1/runnables/{name}/invoke` | Single invocation |
| POST | `/api/v1/runnables/{name}/batch` | Batch invocation |
| GET | `/api/v1/runnables/{name}/stream` | Stream with SSE |

### Built-in Runnables

**`inference`** — Execute AI inference with:
- Data classification (RESTRICTED → local only, else cloud)
- PII masking
- Cost routing (Haiku/Sonnet/Opus)
- Budget enforcement
- Audit logging

Input schema:
```json
{
  "prompt": "string (required)",
  "task_type": "string (required)",
  "team_id": "string (required)",
  "user_id": "string (required)",
  "complexity": "string (optional, default=medium)",
  "trace_id": "string (optional)"
}
```

Output schema:
```json
{
  "output": "string",
  "metadata": {
    "job_id": "string",
    "status": "completed | failed",
    "model_alias": "haiku | sonnet | opus",
    "provider": "anthropic | azure_openai | ollama",
    "tier": "integer (1 | 11 | 3)",
    "cost_usd": "number",
    "data_class": "RESTRICTED | CONFIDENTIAL | INTERNAL | PUBLIC"
  }
}
```

---

## Architecture

### Request Flow

```
Client Request
    ↓
POST /api/v1/runnables/{name}/invoke
    ↓
FastAPI Endpoint (langserve.py)
    ↓
Dependency Injection (InferenceService, RunnableFactory)
    ↓
RunnableFactory.get_schema() — Validate input
    ↓
InferenceService.enqueue() — Create job
    ↓
Poll job status (up to 300x, 1s intervals)
    ↓
Return job result or timeout
    ↓
Response with metadata (cost, provider, status)
```

### Streaming Flow

```
Client Request
    ↓
GET /api/v1/runnables/{name}/stream?input_json=...
    ↓
FastAPI Endpoint (langserve.py, stream_runnable)
    ↓
StreamingResponse (media_type="text/event-stream")
    ↓
Enqueue job + start polling
    ↓
For each token:
  event: token
  data: {"token": "...", "metadata": {...}}
    ↓
On completion:
  event: done
  data: {"output": "...", "metadata": {...}}
    ↓
Client receives streamed events
```

### Governance Flow

All Runnable invocations apply:

1. **Data Classification** → Determines routing (RESTRICTED only to local)
2. **PII Masking** → Redacts sensitive patterns
3. **Cost Routing** → Selects model tier (Haiku/Sonnet/Opus)
4. **Budget Check** → Enforces team cap
5. **Audit Log** → Records team, user, cost, provider
6. **Inference Execution** → Through Tier 1/11/3 providers
7. **Metrics** → Prometheus tracking

---

## Testing Strategy

All tests run in Docker with no local dependencies:

### Unit Tests (test_langserve_runnables.py)
- Runnable factory initialization
- Schema generation
- Pydantic model validation
- Endpoint structure

### Integration Tests (test_langserve_streaming.py)
- SSE event format
- Request/response format compliance
- Data classification routing
- Budget enforcement
- Audit metadata
- Error responses
- Input validation

### E2E Tests (test_langserve_e2e.py)
- Full invocation workflow
- Batch processing
- Streaming response generation
- Provider selection
- Cost tracking
- PII detection
- Error handling

---

## Key Implementation Details

### Synchronous `/invoke` Pattern
- Endpoints enqueue async job
- Poll up to 300 times (5-minute timeout)
- Return result when ready
- Maintains LangServe client compatibility

### Schema Generation
- Auto-generated from Pydantic models
- `InferenceInput` and `InferenceOutput` models
- JSON Schema for client code generation
- No manual schema maintenance

### Server-Sent Events (SSE)
- Content-Type: `text/event-stream`
- Events: `token`, `done`, `error`
- Each event is separate JSON message
- Compatible with LangServe clients

### Error Handling
- `400` — Invalid input (missing required fields)
- `404` — Runnable not found
- `429` — Budget exceeded
- `503` — Service unavailable

---

## Integration Examples

### Python with LangServe

```python
from langserve import RemoteRunnable

runnable = RemoteRunnable("http://localhost:8000/api/v1/runnables/inference")

# Single invocation
result = runnable.invoke({
    "prompt": "Explain this code",
    "task_type": "code_explanation",
    "team_id": "platform",
    "user_id": "alice",
})
print(result["output"])

# Batch
results = runnable.batch([...])

# Streaming
for chunk in runnable.stream({...}):
    if "token" in chunk:
        print(chunk["token"], end="", flush=True)
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

---

## Documentation Files

| File | Purpose |
|------|---------|
| `docs/langserve-api.md` | API reference with all endpoints, error codes, examples |
| `docs/langserve-integration.md` | Integration guide for Python, TypeScript, cURL |
| `docs/PHASE3_IMPLEMENTATION_SUMMARY.md` | What was implemented and why |

---

## Success Criteria (All Met ✅)

✅ LangServe endpoints respond correctly
✅ All built-in Runnables functional
✅ Schema introspection accurate
✅ Streaming works end-to-end
✅ 80+ tests pass in Docker
✅ Data governance fully integrated
✅ No local package installation required
✅ Complete documentation
✅ No breaking changes to Phase 1/2

---

## Status

**Phase 3: LangServe API Surface - COMPLETE**

All implementation, testing, and documentation is complete and ready for production use in Docker.
