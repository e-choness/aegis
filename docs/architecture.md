# Architecture

## System Overview

Aegis is a synchronous-API / asynchronous-execution gateway. Clients receive an HTTP 202 immediately with a `job_id`, then poll `GET /api/v1/jobs/{id}` until the job completes. This keeps connection timeouts off the critical path even for 70B model inference.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client (SDK / curl)                                                │
└───────────────────┬─────────────────────────────────────────────────┘
                    │ POST /api/v1/inference
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI (src/gateway/main.py)                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  InferenceService._run() — asyncio.create_task             │   │
│  │                                                             │   │
│  │  1. DataClassifier.classify()        <1ms regex             │   │
│  │  2. PIIMasker.mask()                 Presidio + CA_SIN      │   │
│  │  3. ModelRouter.route()              rules-based            │   │
│  │  4. BudgetService.check()            pre-flight             │   │
│  │  5. ProviderFactory.get().complete() → LLM call             │   │
│  │  6. PIIMasker.scan_output()          leakage check          │   │
│  │  7. PIIMasker.unmask()               restore entities       │   │
│  │  8. BudgetService.record_spend()     cost accounting        │   │
│  │  9. AuditLogger.log()                TimescaleDB            │   │
│  │  10. Prometheus counters / histograms                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                    │ asyncpg pool (VECTORDB_URL)
                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐
│  Anthropic   │  │  Azure OAI   │  │  vLLM        │  │  Ollama   │
│  (Tier 1A)   │  │  (Tier 1B)   │  │  (Tier 2)    │  │  (Tier 3) │
└──────────────┘  └──────────────┘  └──────────────┘  └───────────┘
```

## Data Classification

`DataClassifier.classify()` runs before any routing decision. It uses regex patterns only — no ML — so latency is guaranteed <1ms and results are deterministic.

| Level | Triggers | Example |
|-------|----------|---------|
| RESTRICTED | Canadian SIN, credit card, account_number keyword | `123-456-789` |
| CONFIDENTIAL | Internal email, api_key keyword, Bearer token, password= | `Bearer eyJ...` |
| INTERNAL | Everything else | Arbitrary business text |
| PUBLIC | Not auto-detected; must be set explicitly by caller | Public documentation |

Classification order is RESTRICTED → CONFIDENTIAL → INTERNAL. A prompt matching both RESTRICTED and CONFIDENTIAL patterns is classified RESTRICTED.

## PIPEDA Hard Invariant

Canadian PIPEDA prohibits RESTRICTED personal data from leaving Canada to US-based providers. This is enforced at two levels:

**Routing layer** (`src/gateway/services/router.py:54`):
```python
if data_classification == DataClassification.RESTRICTED:
    return self._build_config("local", "vllm", "tier2_vllm", 2)
```
RESTRICTED data always returns a Tier 2 (vLLM) or Tier 3 (Ollama) config — never Tier 1.

**Compliance alert** (`src/gateway/services/inference.py:145`):
```python
if classification == "RESTRICTED" and tier == 1:
    restricted_data_cloud_violations_total.inc()
    logger.critical(...)
```
The `restricted_data_cloud_violations_total` Prometheus counter must always remain 0. A non-zero value is a compliance violation.

The compliance invariant view in TimescaleDB (`scripts/init_db.sql`) mirrors this:
```sql
CREATE OR REPLACE VIEW restricted_cloud_violations AS
    SELECT * FROM inference_audit_log
    WHERE data_class = 'RESTRICTED' AND tier = 1;
```
This view must always return 0 rows.

## Provider Selection and Fallback

`ModelRouter` resolves a `ModelConfig` (provider + model_id + cost rates). The fallback chain is tried in order, skipping unhealthy providers:

```
Anthropic (1A) → Azure OpenAI (1B) → vLLM (2) → Ollama (3)
```

**Routing rules (in priority order):**

1. RESTRICTED → force `local` alias at Tier 2 (vLLM), regardless of task or budget
2. Task type maps to alias: `commit_summary` → haiku, `pr_review` → sonnet, `security_audit` → opus
3. Complexity escalation: `security_audit` + `high` complexity → opus
4. Budget degradation: opus with <$1.00 remaining → sonnet

## Model Registry

`config/model_registry.yaml` is the single source of truth for all model IDs and pricing. The router never hardcodes model strings — it always reads from the registry.

```yaml
opus:
  tier1_anthropic: "claude-opus-4-7"
  tier2_vllm:      "devstral-small:24b-q5_K_M"
  tier3_ollama:    "devstral-small:24b-q4_K_M"
  cost_input_per_mtok:  5.00
  cost_output_per_mtok: 25.00
  tokenizer_margin: 1.35   # Opus 4.7 tokenizer generates up to 35% more tokens
```

The `tokenizer_margin` on opus (1.35×) is applied to cost estimates because the Opus 4.7 tokenizer generates measurably more tokens than earlier models. Sonnet and Haiku use margin 1.0.

## PII Masking

`PIIMasker` wraps Microsoft Presidio with a custom `CA_SIN` recognizer (three patterns: dashes, spaces, plain 9-digit). Masking works right-to-left so that replacing entity spans doesn't shift the offsets of earlier (higher-index) spans.

The `restore_map` maps each generated placeholder back to the original text. `scan_output()` runs the same analyzer on the provider response to catch accidental PII leakage before the response is returned to the caller.

## Circuit Breaker

`ProviderHealth` implements a simple token-bucket circuit breaker per provider:
- 3 consecutive failures → circuit opens, provider marked unhealthy
- 60 seconds after opening → half-open (one probe attempt)
- Successful probe → circuit closes, failure count resets

The router skips unhealthy providers when walking the fallback chain.

## RAG Service

`RAGService` provides document indexing and retrieval backed by pgvector. Enabled only when `VECTORDB_URL` is set at startup.

**Embedding routing** follows the same PIPEDA invariant as inference:

| Classification | Embedding provider | Dimensions |
|---------------|-------------------|------------|
| RESTRICTED | vLLM (BGE-M3) else Ollama (nomic-embed-text) | 768 |
| CONFIDENTIAL | vLLM else Ollama | 768 |
| INTERNAL | vLLM else OpenAI else Ollama | 768 or 1536 |
| PUBLIC | OpenAI else vLLM else Ollama | 1536 or 768 |

**ADR-008:** 768-dim is the canonical index dimension for RESTRICTED/CONFIDENTIAL data. Never mix 768-dim and 1536-dim vectors in the same pgvector index — query results will be meaningless.

Retrieval enforces classification hierarchy: a query at `INTERNAL` level can only retrieve chunks with classification `PUBLIC` or `INTERNAL` — never `CONFIDENTIAL` or `RESTRICTED`.

## Databases

| Database | Image | Port | Purpose |
|----------|-------|------|---------|
| TimescaleDB | `timescale/timescaledb:latest-pg16` | 5432 | Inference audit log (hypertable) |
| pgvector | `pgvector/pgvector:pg16` | 5433 | RAG document chunk vectors |

## Observability Stack

Prometheus scrapes `GET /metrics` every 15 seconds. Grafana reads from Prometheus. The Prometheus datasource is auto-provisioned via `grafana/provisioning/datasources/prometheus.yml`.

Key alert conditions (configure in Grafana):
- `restricted_data_cloud_violations_total > 0` — CRITICAL compliance alert
- `provider_health_up{provider="anthropic"} == 0` — primary provider down
- `budget_utilization_ratio > 0.90` — team approaching budget cap
