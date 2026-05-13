# API Reference

Base URL: `http://localhost:8000`

All inference endpoints follow an **async job pattern**: `POST` returns `202 Accepted` with a `job_id`, then poll `GET /jobs/{id}` until `status` is `completed` or `failed`.

Interactive docs (Swagger UI) available at http://localhost:8000/docs.

---

## Table of Contents

- [Health](#health)
- [Inference](#inference)
- [Jobs](#jobs)
- [RAG — Index](#rag--index)
- [RAG — Query](#rag--query)
- [Workflows](#workflows)
- [Tools](#tools)
- [Conversations](#conversations)
- [Metrics](#metrics)
- [Task Types](#task-types)
- [Data Classifications](#data-classifications)
- [Error Codes](#error-codes)

---

## Health

### `GET /api/v1/health`

Returns gateway and provider health status.

**Response `200`**

```json
{
  "status": "ok",
  "providers": {
    "anthropic": true,
    "azure_openai": false,
    "ollama": true
  },
  "restricted_cloud_violations": 0
}
```

| Field | Description |
|-------|-------------|
| `status` | `"ok"` or `"degraded"` |
| `providers` | Per-provider circuit breaker state |
| `restricted_cloud_violations` | Compliance counter — must always be `0` |

---

## Inference

### `POST /api/v1/inference`

Submit an AI inference request. Returns immediately with a `job_id`.

**Request body**

```json
{
  "prompt": "Review this pull request for security issues.",
  "task_type": "security_audit",
  "team_id": "platform",
  "user_id": "alice",
  "data_classification": "INTERNAL",
  "complexity": "medium",
  "max_tokens": 1024
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | **Yes** | — | The prompt text |
| `task_type` | string | **Yes** | — | See [Task Types](#task-types) |
| `team_id` | string | **Yes** | — | Team for budget tracking |
| `user_id` | string | **Yes** | — | Requesting user (audit trail) |
| `data_classification` | string | No | Auto-detected | Override classification |
| `complexity` | string | No | `"medium"` | `"low"` \| `"medium"` \| `"high"` |
| `max_tokens` | integer | No | `1024` | Maximum response tokens |

**Response `202 Accepted`**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

**Errors**

| Code | Reason |
|------|--------|
| `400` | Missing required fields or invalid task_type |
| `429` | Team budget cap exceeded |
| `503` | All providers unavailable |

---

## Jobs

### `GET /api/v1/jobs/{job_id}`

Poll the status of an inference job.

**Response `200`**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "result": "The code looks secure. No SQL injection or XSS vulnerabilities found.",
  "model_alias": "sonnet",
  "provider": "anthropic",
  "tier": 1,
  "data_class": "INTERNAL",
  "cost_usd": 0.0023,
  "latency_ms": 1240,
  "created_at": "2026-05-04T22:00:00Z",
  "completed_at": "2026-05-04T22:00:01Z"
}
```

| Field | Description |
|-------|-------------|
| `status` | `"pending"` \| `"completed"` \| `"failed"` |
| `result` | LLM response text (present when `completed`) |
| `error` | Error message (present when `failed`) |
| `model_alias` | Logical model tier used (`haiku`, `sonnet`, `opus`) |
| `provider` | Actual provider (`anthropic`, `azure_openai`, `ollama`) |
| `tier` | Provider tier (1 = cloud, 3 = local) |
| `data_class` | Effective classification applied to this request |
| `cost_usd` | Actual cost of this request |

**Polling recommendation:** start at 500ms, back off to 2s. Both SDKs handle this automatically.

---

## RAG — Index

### `POST /api/v1/rag/index`

Index a document for retrieval-augmented generation.

**Request body**

```json
{
  "document_id": "policy-handbook-v3",
  "content": "Full document text here...",
  "data_classification": "INTERNAL",
  "namespace": "hr-policies"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `document_id` | string | **Yes** | — | Unique identifier for the document |
| `content` | string | **Yes** | — | Full document text to index |
| `data_classification` | string | No | `"INTERNAL"` | Controls which embedding provider is used |
| `namespace` | string | No | `"default"` | Logical namespace for retrieval scoping |

**Response `201 Created`**

```json
{
  "document_id": "policy-handbook-v3",
  "chunks_indexed": 4
}
```

**Notes:**
- Documents are split into 400-word chunks with 50-word overlap
- Indexing is idempotent (`ON CONFLICT DO NOTHING` per document_id + chunk_index)
- `RESTRICTED`/`CONFIDENTIAL` documents always use local Ollama embeddings (768-dim)
- The embedding model (`nomic-embed-text`) is auto-pulled on first use

---

## RAG — Query

### `POST /api/v1/rag/query`

Retrieve relevant chunks for a question.

**Request body**

```json
{
  "question": "What is the remote work reimbursement limit?",
  "namespace": "hr-policies",
  "data_classification": "INTERNAL",
  "top_k": 5
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | **Yes** | — | Natural language question |
| `namespace` | string | No | `"default"` | Namespace to search within |
| `data_classification` | string | No | `"INTERNAL"` | Controls retrieval access level |
| `top_k` | integer | No | `5` | Number of chunks to return |

**Response `200`**

```json
{
  "context": "[Source 1] (similarity=0.87)\nEmployees working remotely may expense...\n\n---\n\n[Source 2] (similarity=0.74)\nThe monthly cap for home office equipment...",
  "chunks": [
    {
      "chunk_index": 2,
      "content": "Employees working remotely may expense...",
      "data_class": "INTERNAL",
      "similarity": 0.8712
    }
  ],
  "chunk_count": 2
}
```

| Field | Description |
|-------|-------------|
| `context` | Pre-formatted string for direct inclusion in an LLM prompt |
| `chunks` | Raw chunk list with similarity scores |
| `chunk_count` | Number of chunks returned |

**Access control:** a query at classification level N cannot retrieve chunks at level N+1 or higher. `PUBLIC` cannot see `INTERNAL` chunks.

**Errors**

| Code | Reason |
|------|--------|
| `503` | RAG service not configured (`VECTORDB_URL` not set) |

---

## Workflows

Phase 2 workflow endpoints require tenant headers:

| Header | Description |
|--------|-------------|
| `X-Team-ID` | Calling team namespace |
| `X-User-ID` | Calling user id |

### `GET /api/v1/workflows/list`

Lists configured workflow definitions from `config/workflows.yaml`.

### `POST /api/v1/workflows/{workflow_id}/execute`

Executes or queues an agentic workflow.

```json
{
  "input_data": {"query": "What is RAG?", "max_results": 2},
  "tools": ["web_search"],
  "async_mode": false,
  "queue": false,
  "priority": 5
}
```

Returns `202 Accepted` with either `workflow_instance_id` or `queue_id`.

### `GET /api/v1/workflows/instances/{workflow_instance_id}`

Returns workflow status, output, cost, tool-call count, and conversation id. Cross-team reads return `404`.

### `GET /api/v1/workflows/instances/{workflow_instance_id}/history`

Returns the persisted user and assistant messages for a workflow instance.

### `POST /api/v1/workflows/instances/{workflow_instance_id}/resume`

Adds user input and resumes the workflow from its latest state.

### `DELETE /api/v1/workflows/instances/{workflow_instance_id}`

Cancels a workflow instance.

## Tools

### `GET /api/v1/tools/list`

Lists tools available to the calling team.

### `GET /api/v1/tools/{tool_name}`

Returns a tool definition and JSON schemas.

### `POST /api/v1/tools/{tool_name}/validate`

Validates arguments without executing the tool.

```json
{
  "args": {"query": "aegis", "max_results": 1}
}
```

### `POST /api/v1/tools/{tool_name}/execute`

Debug-only direct execution. Requires `admin` permission in the team context.

## Conversations

### `GET /api/v1/conversations`

Lists team-scoped workflow conversations.

### `GET /api/v1/conversations/{conversation_id}`

Returns conversation metadata, state, and message count.

### `GET /api/v1/conversations/{conversation_id}/messages`

Returns conversation messages.

### `POST /api/v1/conversations/{conversation_id}/export?format=json|markdown`

Exports the conversation.

### `DELETE /api/v1/conversations/{conversation_id}`

Archives the conversation for the calling team.

## Metrics

### `GET /metrics`

Prometheus text format scrape endpoint.

```
# HELP gateway_requests_total Total inference requests
# TYPE gateway_requests_total counter
gateway_requests_total{team_id="platform",model_alias="sonnet",provider="anthropic",tier="1",status="completed"} 42

# HELP restricted_data_cloud_violations_total PIPEDA violations (must stay 0)
# TYPE restricted_data_cloud_violations_total counter
restricted_data_cloud_violations_total 0
```

---

## Task Types

| Task Type | Default Model | Use Case |
|-----------|--------------|---------|
| `commit_summary` | Haiku | Summarize a git commit |
| `simple_qa` | Haiku | Simple question answering |
| `routing` | Haiku | Intent classification |
| `classification` | Haiku | Text classification |
| `pr_review` | Sonnet | Pull request code review |
| `rag_response` | Sonnet | Answer using retrieved context |
| `code_explanation` | Sonnet | Explain a code snippet |
| `documentation` | Sonnet | Generate documentation |
| `deployment_check` | Sonnet | Validate deployment config |
| `security_audit` | Opus | Security vulnerability analysis |
| `architecture_review` | Opus | High-level design review |
| `multi_file_refactor` | Opus | Complex multi-file changes |

Unknown task types default to `sonnet`.

---

## Data Classifications

| Value | Description | Cloud Allowed |
|-------|-------------|---------------|
| `PUBLIC` | No sensitive patterns | Yes |
| `INTERNAL` | Default for unclassified data | Yes |
| `CONFIDENTIAL` | API keys, tokens, internal credentials | Yes |
| `RESTRICTED` | SIN, credit cards, account numbers | **Never** |

If `data_classification` is omitted from the request, it is auto-detected from the prompt content using regex patterns in `DataClassifier`.

---

## Error Codes

| HTTP Status | Meaning |
|-------------|---------|
| `202` | Request accepted, poll `GET /jobs/{id}` for result |
| `201` | Document indexed successfully |
| `400` | Bad request — invalid fields or missing required params |
| `404` | Job ID not found |
| `429` | Team budget cap exceeded — retry after budget resets |
| `503` | Service unavailable — RAG not configured, or all providers down |
| `500` | Unexpected internal error — check `make logs` |
