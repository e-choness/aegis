# Aegis AI Gateway

The Aegis platform is the centralized control plane for all enterprise AI interactions. It transforms fragmented, ad-hoc LLM integrations into a governed, secure, and cost-optimized service layer. Provider-agnostic, config-driven, and Docker-native — like OpenClaude, but with enterprise governance.

**103 tests passing · 100% Docker — no host installs required**

---

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 2. Run all tests inside Docker
make test

# 3. Start the full stack
make up
# Gateway: http://localhost:8000
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001  (admin / admin)
```

---

## What It Does

```
Client → POST /api/v1/inference
            │
            ▼
      DataClassifier          ← regex, <1ms, RESTRICTED/CONFIDENTIAL/INTERNAL/PUBLIC
            │
            ▼
      PIIMasker               ← Presidio + CA_SIN
            │
            ▼
      ModelRouter             ← task type + classification + budget → ModelConfig
            │
            ▼
      ProviderFactory         ← Anthropic → Azure OpenAI → Ollama (local)
            │
            ▼
      scan_output             ← PII leakage check
            │
            ▼
      unmask                  ← restore masked entities
            │
            ▼
      AuditLogger + Metrics   ← TimescaleDB + Prometheus
            │
            ▼
      GET /api/v1/jobs/{id}   ← poll until completed / failed
```

**PIPEDA hard invariant:** `RESTRICTED` data (SIN, credit card, account numbers) never reaches a cloud provider. This is enforced as a code-level routing invariant in `ModelRouter.route()` and tested as `test_restricted_routing_invariant`.

---

## Provider Tiers

| Tier | Provider | Data classes allowed | Notes |
| ---- | ------------------- | -------------------- | --------------------------- |
| 1A   | Anthropic           | INTERNAL, PUBLIC     | Default cloud path          |
| 1B   | Azure OpenAI Canada | INTERNAL, PUBLIC     | Canadian region fallback    |
| 2/3  | Ollama (local)      | ALL incl. RESTRICTED | Final fallback, user-configured endpoint |

Circuit breaker: 3 failures in 60s opens circuit, resets after 60s half-open.

---

## Repository Layout

```
Aegis/
├── src/gateway/               # FastAPI application
│   ├── main.py                # App lifecycle, middleware, router registration
│   ├── models.py              # Pydantic models (InferenceRequest, JobResult, …)
│   ├── providers/
│   │   ├── base.py            # LLMProvider ABC
│   │   ├── factory.py         # ProviderFactory.get(name)
│   │   ├── anthropic_provider.py
│   │   ├── azure_openai_provider.py
│   │   └── ollama_provider.py
│   └── services/
│       ├── classifier.py      # DataClassifier — regex, <1ms
│       ├── router.py          # ModelRouter — task/complexity/budget → ModelConfig
│       ├── pii.py             # PIIMasker — Presidio + CA_SIN
│       ├── inference.py       # InferenceService — full pipeline orchestrator
│       ├── rag.py             # TextChunker + RAGService (pgvector)
│       ├── audit.py           # AuditLogger
│       ├── budget.py          # BudgetService — per-team monthly caps
│       └── health.py          # ProviderHealth — circuit breaker
│   └── api/v1/
│       ├── inference.py       # POST /inference, GET /jobs/{id}
│       ├── health.py          # GET /health
│       └── rag.py             # POST /rag/index, POST /rag/query
├── evals/                     # Model evaluation framework
├── tests/                     # 103 pytest tests
├── sdk/
│   ├── python/                # Python SDK (aegis-sdk)
│   └── typescript/            # TypeScript SDK (@aegis/ai-platform-client)
├── config/
│   └── model_registry.yaml    # ← SINGLE SOURCE OF TRUTH for model IDs
├── scripts/
│   ├── init_db.sql            # TimescaleDB schema (audit log, hypertable)
│   └── init_vectordb.sql      # pgvector schema (768-dim RAG index)
├── prometheus/
├── grafana/
├── docker-compose.yml         # Gateway + Postgres + Prometheus + Grafana
└── Makefile
```

---

## Environment Variables

| Variable                    | Required | Default                 | Description                                   |
| --------------------------- | -------- | ----------------------- | --------------------------------------------- |
| `ANTHROPIC_API_KEY`       | Yes      | —                      | Tier 1A cloud provider                        |
| `AZURE_OPENAI_ENDPOINT`   | No       | —                      | Tier 1B; disables Azure if unset              |
| `AZURE_OPENAI_KEY`        | No       | —                      | Tier 1B API key                               |
| `OLLAMA_BASE_URL`         | No       | `http://localhost:11434`| Local LLM endpoint (user-configured)          |
| `VECTORDB_URL`            | No       | —                      | PostgreSQL DSN for RAG; disables RAG if unset |
| `TIMESCALEDB_PASSWORD`    | No       | `aegis_dev`           | Audit database                                |
| `CORS_ORIGINS`            | No       | `""`                  | Comma-separated allowed origins               |
| `GRAFANA_PASSWORD`        | No       | `admin`               | Grafana admin password                        |

---

## Make Targets

```bash
make build        # Build all Docker images
test             # Run all tests (gateway) in Docker
up               # Start gateway + all dependencies
down             # Stop all containers
logs             # Tail gateway logs
shell            # Interactive shell inside gateway container
```

---

## SDKs

### Python

```python
from aegis_sdk import AIPlatformClient, InferenceRequest, PollOptions

async with AIPlatformClient(sso_token=token, base_url="http://localhost:8000") as client:
    job_id = await client.submit_inference(
        InferenceRequest(prompt="Review this diff", task_type="pr_review",
                         team_id="platform", user_id="alice")
    )
    result = await client.poll_job(job_id, PollOptions(timeout=90.0))
    print(result.result)
```

### TypeScript

```typescript
import { AIPlatformClient } from "@aegis/ai-platform-client";

const client = new AIPlatformClient({ ssoToken: token, baseUrl: "http://localhost:8000" });
const jobId = await client.submitInference({ 
  prompt: "...",
  task_type: "pr_review",
  team_id: "platform",
  user_id: "alice"
});
const result = await client.pollJob(jobId);
```

---

## Observability

| Metric                                     | Type      | Labels                                       |
| ------------------------------------------ | --------- | -------------------------------------------- |
| `gateway_requests_total`                 | Counter   | team_id, model_alias, provider, tier, status |
| `inference_cost_usd_total`               | Counter   | team_id, model_alias, provider, tier         |
| `pii_detections_total`                   | Counter   | entity_type                                  |
| `restricted_data_cloud_violations_total` | Counter   | — (must stay 0)                             |
| `gateway_inference_latency_seconds`      | Histogram | model_alias, provider                        |
| `provider_health_up`                     | Gauge     | provider, tier                               |
| `budget_utilization_ratio`               | Gauge     | team_id                                      |

Scrape endpoint: `GET /metrics` (Prometheus text format)

---

## Developer Docs

- [Architecture](docs/architecture.md) — design decisions, data flow, PIPEDA invariant
- [API Reference](docs/api.md) — REST endpoints, request/response schemas
- [Development Guide](docs/development.md) — adding providers, running tests, extending evals
