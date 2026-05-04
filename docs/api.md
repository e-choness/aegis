# API Reference

Base URL: `http://localhost:8000` (development)

All inference endpoints follow the async job pattern: POST returns 202 + `job_id`, then poll GET until `status` is `completed` or `failed`.

---

## POST /api/v1/inference

Submit an inference job.

**Request body**

```json
{
  "prompt":     "string (required)",
  "task_type":  "string (default: general)",
  "team_id":    "string (required)",
  "user_id":    "string (required)",
  "complexity": "low | medium | high (default: medium)",
  "trace_id":   "string (optional, UUID)"
}
```

**Task types and default model alias**

| task_type | Alias | Notes |
|-----------|-------|-------|
| `commit_summary` | haiku | |
| `simple_qa` | haiku | |
| `routing` | haiku | |
| `classification` | haiku | |
| `pr_review` | sonnet | Prepends code-review system prompt |
| `rag_response` | sonnet | |
| `code_explanation` | sonnet | |
| `documentation` | sonnet | |
| `deployment_check` | sonnet | |
| `security_audit` | opus | Escalates to opus on `complexity=high` |
| `architecture_review` | opus | |
| `multi_file_refactor` | opus | |
| _(anything else)_ | sonnet | Default fallback |

**Response 202**

```json
{
  "job_id":   "550e8400-e29b-41d4-a716-446655440000",
  "status":   "queued",
  "trace_id": "string or null"
}
```

**Error responses**

| Code | Condition |
|------|-----------|
| 400 | Missing `team_id` or `user_id` |
| 402 | Team budget exceeded |
| 451 | RESTRICTED data routed to cloud (compliance violation — should never occur) |

---

## GET /api/v1/jobs/{job_id}

Poll for job status.

**Response 200**

```json
{
  "job_id":              "string",
  "status":              "queued | running | completed | failed",
  "content":             "string or null",
  "model_alias":         "haiku | sonnet | opus | local",
  "provider":            "anthropic | azure_openai | vllm | ollama",
  "tier":                1,
  "cost_usd":            0.0023,
  "data_classification": "RESTRICTED | CONFIDENTIAL | INTERNAL | PUBLIC",
  "error":               "string or null"
}
```

**Response 404** — job_id not found.

---

## GET /api/v1/health

Returns gateway health and provider status.

**Response 200**

```json
{
  "status": "ok",
  "providers": {
    "anthropic":    true,
    "azure_openai": true,
    "vllm":         false,
    "ollama":       true
  },
  "restricted_cloud_violations": 0
}
```

`restricted_cloud_violations` must always be 0. A non-zero value is a PIPEDA compliance incident.

---

## POST /api/v1/rag/index

Index a document for RAG retrieval. Requires `VECTORDB_URL` to be set; returns 503 otherwise.

**Request body**

```json
{
  "document_id":       "string (required)",
  "content":           "string (required)",
  "data_classification": "INTERNAL",
  "namespace":         "default"
}
```

**Response 201**

```json
{
  "document_id":   "string",
  "chunks_indexed": 3
}
```

Documents are chunked at word boundaries (~400 words, 50-word overlap). Each chunk is embedded using the provider selected by `data_classification`. RESTRICTED/CONFIDENTIAL documents use the 768-dim on-prem index only.

---

## POST /api/v1/rag/query

Retrieve relevant chunks for a query.

**Request body**

```json
{
  "question":          "string (required)",
  "namespace":         "default",
  "data_classification": "INTERNAL",
  "top_k":             5
}
```

**Response 200**

```json
{
  "context":     "Formatted string with [Source N] headers",
  "chunks":      [
    {
      "chunk_index": 0,
      "content":     "string",
      "data_class":  "INTERNAL",
      "similarity":  0.91
    }
  ],
  "chunk_count": 1
}
```

Retrieval respects the classification hierarchy: a query at `INTERNAL` cannot retrieve chunks classified as `CONFIDENTIAL` or `RESTRICTED`.

---

## GET /metrics

Prometheus text-format metrics. Not included in the OpenAPI schema.

---

## Error Response Shape

All 4xx/5xx responses from the gateway follow FastAPI's default error format:

```json
{
  "detail": "human-readable error message"
}
```

The `x-trace-id` response header is set on all inference responses for distributed tracing. Both SDKs surface this as `trace_id` on error objects.
