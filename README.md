# Aegis AI Gateway

The Aegis platform is the centralized control plane for all enterprise AI interactions. It transforms fragmented, ad-hoc LLM integrations into a governed, secure, and cost-optimized service layer. We are not just an API wrapper; we are the AI Governance Gateway that ensures every token spent adheres to regulatory, security, and financial policies.

Enterprise AI governance gateway for Canadian fintech. Routes LLM requests through a four-tier provider fallback chain while enforcing PIPEDA data residency, per-team budget caps, PII masking, and a full audit trail.

**112 gateway tests · 14 Python SDK tests · 100% Docker — no host installs required**

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
     PIIMasker               ← Presidio + custom CA_SIN recognizer
           │
     ModelRouter             ← task type + classification + budget → ModelConfig
           │
     ProviderFactory         ← Anthropic → Azure OpenAI → vLLM → Ollama
           │
     scan_output             ← PII leakage check on response
           │
     unmask                  ← restore masked entities
           │
     AuditLogger + Metrics   ← TimescaleDB + Prometheus
           │
           ▼
     GET /api/v1/jobs/{id}   ← poll until completed / failed
```

**PIPEDA hard invariant:** `RESTRICTED` data (SIN, credit card numbers, account references) never reaches a cloud provider. This is enforced as a code-level routing invariant in `ModelRouter.route()` and tested as `test_restricted_routing_invariant`.

---

## Provider Tiers

| Tier | Provider            | Data classes allowed | Notes                       |
| ---- | ------------------- | -------------------- | --------------------------- |
| 1A   | Anthropic           | INTERNAL, PUBLIC     | Default cloud path          |
| 1B   | Azure OpenAI Canada | INTERNAL, PUBLIC     | Canadian region fallback    |
| 2    | vLLM (self-hosted)  | ALL incl. RESTRICTED | 2× A100 80GB, 300s timeout |
| 3    | Ollama (offline)    | ALL incl. RESTRICTED | Final fallback, no network  |

Circuit breaker: 3 failures in 60s opens circuit, resets after 60s half-open.

---

## Repository Layout

```
Aegis/
├── src/gateway/               # FastAPI application
│   ├── main.py                # App lifecycle, middleware, router registration
│   ├── models.py              # Pydantic models (InferenceRequest, JobResult, …)
│   ├── telemetry.py           # Prometheus counters / histograms / gauges
│   ├── api/v1/
│   │   ├── inference.py       # POST /inference, GET /jobs/{id}
│   │   ├── health.py          # GET /health
│   │   └── rag.py             # POST /rag/index, POST /rag/query
│   ├── providers/
│   │   ├── base.py            # LLMProvider ABC
│   │   ├── factory.py         # ProviderFactory.get(name)
│   │   ├── anthropic_provider.py
│   │   ├── azure_openai_provider.py
│   │   ├── ollama_provider.py
│   │   ├── vllm_provider.py
│   │   └── embeddings/        # EmbeddingProvider ABC + per-provider impls + factory
│   └── services/
│       ├── classifier.py      # DataClassifier — regex, <1ms
│       ├── router.py          # ModelRouter — task/complexity/budget → ModelConfig
│       ├── pii.py             # PIIMasker — Presidio + CA_SIN
│       ├── inference.py       # InferenceService — full pipeline orchestrator
│       ├── rag.py             # TextChunker + RAGService (pgvector)
│       ├── audit.py           # AuditLogger
│       ├── budget.py          # BudgetService — per-team monthly caps
│       └── health.py          # ProviderHealth — circuit breaker
├── evals/                     # Model evaluation framework
│   ├── golden_dataset.py      # 10 labelled cases (security/perf/style/fp)
│   ├── scorer.py              # Precision / recall / F1
│   └── runner.py              # run_eval() with injectable review_fn
├── tests/                     # 112 pytest tests
├── sdk/
│   ├── python/                # Python SDK (aegis-sdk)
│   └── typescript/            # TypeScript SDK (@aegis/ai-platform-client)
├── config/
│   └── model_registry.yaml    # Model IDs and pricing — single source of truth
├── scripts/
│   ├── init_db.sql            # TimescaleDB schema (audit log, hypertable)
│   └── init_vectordb.sql      # pgvector schema (768-dim RAG index)
├── prometheus/prometheus.yml
├── grafana/provisioning/
├── Dockerfile                 # Multi-stage: base → deps → app → test / runtime
├── docker-compose.yml
└── Makefile
```

---

## Environment Variables

| Variable                    | Required | Default                 | Description                                   |
| --------------------------- | -------- | ----------------------- | --------------------------------------------- |
| `ANTHROPIC_API_KEY`       | Yes      | —                      | Tier 1A cloud provider                        |
| `AZURE_OPENAI_ENDPOINT`   | No       | —                      | Tier 1B; disables Azure if unset              |
| `AZURE_OPENAI_KEY`        | No       | —                      | Tier 1B API key                               |
| `AZURE_OPENAI_DEPLOYMENT` | No       | —                      | Azure deployment name                         |
| `VLLM_BASE_URL`           | No       | `http://vllm:8001`    | Tier 2 on-prem                                |
| `OLLAMA_BASE_URL`         | No       | `http://ollama:11434` | Tier 3 offline                                |
| `VECTORDB_URL`            | No       | —                      | PostgreSQL DSN for RAG; disables RAG if unset |
| `TIMESCALEDB_PASSWORD`    | No       | `aegis_dev`           | Audit database                                |
| `VECTORDB_PASSWORD`       | No       | `aegis_vec`           | pgvector database                             |
| `CORS_ORIGINS`            | No       | `""`                  | Comma-separated allowed origins               |
| `GRAFANA_PASSWORD`        | No       | `admin`               | Grafana admin password                        |

---

## Make Targets

```bash
make build        # Build all Docker images
make test         # Run all tests (gateway + SDKs) in Docker
make test-py      # Gateway tests only
make test-sdk-py  # Python SDK tests only
make test-ts      # TypeScript SDK tests only
make up           # Start gateway + all dependencies
make down         # Stop all containers
make logs         # Tail gateway logs
make shell        # Interactive shell inside gateway container
```

---

## SDKs

### Python

```python
from aegis_sdk import AIPlatformClient, InferenceRequest, PollOptions

async with AIPlatformClient(sso_token="...", base_url="http://gateway:8000") as client:
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

const client = new AIPlatformClient({ ssoToken: "...", baseUrl: "http://gateway:8000" });
const jobId = await client.submitInference({ prompt: "...", task_type: "pr_review",
                                             team_id: "platform", user_id: "alice" });
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
- [Development Guide](docs/development.md) — adding providers, running tests, extending the eval suite
