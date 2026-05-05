# Architecture

> Deep-dive on Aegis design decisions, data flow, and compliance invariants.

---

## Table of Contents

- [Design Goals](#design-goals)
- [Request Lifecycle](#request-lifecycle)
- [Data Classification](#data-classification)
- [Provider Tiers & Routing](#provider-tiers--routing)
- [PIPEDA Invariant](#pipeda-invariant)
- [PII Protection](#pii-protection)
- [RAG Pipeline](#rag-pipeline)
- [Observability](#observability)
- [Budget Enforcement](#budget-enforcement)
- [Circuit Breaker](#circuit-breaker)
- [Async Job Model](#async-job-model)
- [Config-Driven Model Registry](#config-driven-model-registry)
- [Scaling Path](#scaling-path)

---

## Design Goals

| Goal | Implementation |
|------|---------------|
| Provider-agnostic | `LLMProvider` ABC + `ProviderFactory` — swap providers via config, zero code changes |
| Zero cloud for RESTRICTED data | Hard routing invariant in `ModelRouter.route()`, tested, Prometheus-monitored |
| Sub-2ms governance overhead | Regex-only classification, rules-based routing — no ML in the hot path |
| Config-driven model selection | `config/model_registry.yaml` is the single source of truth for model IDs and costs |
| Auditable by design | Every inference writes a timestamped audit record to TimescaleDB |
| Solo-buildable | Docker Compose, CPU-only, no GPU required |

---

## Request Lifecycle

```mermaid
flowchart TD
    A(["POST /api/v1/inference"])

    B["1. DataClassifier\nregex · &lt;1ms\nRESTRICTED · CONFIDENTIAL · INTERNAL · PUBLIC"]

    C["2. PIIMasker.mask()\nreplace entities with typed placeholders\nstore entity map for later restoration"]

    D["3. ModelRouter.route()\ntask_type · complexity · classification · budget\n→ ModelConfig { provider, model_id, tier, cost_per_mtok }"]

    E{"4. BudgetService.check()\nestimated cost vs team cap"}
    F(["HTTP 429\nBudget exceeded"])

    G["5. ProviderFactory.get()\nAnthropicProvider · AzureOpenAIProvider · OllamaProvider"]

    H["6. PIIMasker.scan() + unmask()\ndetect PII leakage in response\nrestore original entities via entity map"]

    I["7. AuditLogger + Prometheus\nwrite timestamped audit row\nincrement counters + histograms"]

    J(["202 Accepted → { job_id }"])
    K(["GET /api/v1/jobs/{job_id}\npoll until completed · failed"])

    A --> B --> C --> D --> E
    E -->|"under cap"| G
    E -->|"over cap"| F
    G --> H --> I --> J --> K
```

---

## Data Classification

`DataClassifier` uses compiled regex patterns. No ML in this path — zero latency variance, zero false negatives for known patterns.

| Level | Patterns | Examples |
|-------|----------|---------|
| `RESTRICTED` | Canadian SIN, credit cards, account numbers | `123-456-789`, `4111 1111 1111 1111` |
| `CONFIDENTIAL` | Internal email, API keys, bearer tokens, password assignments | `api_key=...`, `Bearer eyJ...` |
| `INTERNAL` | Default — no RESTRICTED or CONFIDENTIAL match | Most business prompts |
| `PUBLIC` | Explicitly set via `data_classification` request field | Documentation queries |

Classification applies to the **prompt only**. The LLM response is scanned separately for PII leakage.

---

## Provider Tiers & Routing

`ModelRouter` maps `(task_type, complexity, data_classification, budget_remaining_usd)` to a `ModelConfig`. All rules are explicit — no ML, fully deterministic.

```mermaid
flowchart TD
    IN(["ModelRouter.route()\ntask_type · complexity · classification · budget"])

    R{"RESTRICTED?"}
    OLL3["Ollama Tier 3\nHARD INVARIANT\nreturns immediately"]

    B{"budget &lt; $1\nAND alias = opus?"}
    DOWN["Downgrade to Sonnet\nBUDGET DEGRADATION"]

    C{"complexity = high\nAND task = security_audit?"}
    ESC["Escalate to Opus\nCOMPLEXITY ESCALATION"]

    MAP["TASK_ALIAS_MAP\ncommit_summary · simple_qa · routing → haiku\npr_review · rag_response · code_explain → sonnet\nsecurity_audit · architecture_review → opus"]

    CHAIN["FALLBACK_CHAIN\nhealth-aware provider selection"]
    ANT["✅ Anthropic\nTier 1A"]
    AZ["✅ Azure OpenAI Canada\nTier 1B"]
    OLL["✅ Ollama\nTier 2/3"]

    IN --> R
    R -->|"Yes"| OLL3
    R -->|"No"| B
    B -->|"Yes"| DOWN
    B -->|"No"| C
    C -->|"Yes"| ESC
    C -->|"No"| MAP
    DOWN & ESC & MAP --> CHAIN
    CHAIN --> ANT
    ANT -->|"circuit open"| AZ
    AZ -->|"circuit open"| OLL
```

**Model IDs are never hardcoded** in routing logic. `_build_config()` always looks up `config/model_registry.yaml`. Upgrading from `claude-sonnet-4-6` to a future version requires editing one YAML key.

---

## PIPEDA Invariant

RESTRICTED data must never be sent to a cloud provider. This is enforced at four independent layers.

### Layer 1 — Routing Code

```python
# src/gateway/services/router.py
if data_classification == DataClassification.RESTRICTED:
    return self._build_config("local", "ollama", "tier3_ollama", 3)
    # Returns immediately. No further routing logic runs.
```

### Layer 2 — Compliance Counter

```python
# src/gateway/services/inference.py
if result.data_class == "RESTRICTED" and result.tier == 1:
    restricted_violations_total.inc()  # Prometheus CRITICAL alert fires
```

### Layer 3 — Database View

```sql
-- scripts/init_db.sql
CREATE VIEW restricted_cloud_violations AS
  SELECT * FROM audit_log WHERE class = 'RESTRICTED' AND tier = 1;
-- Query must always return 0 rows
```

### Layer 4 — Automated Tests

```
test_restricted_routing_invariant
test_restricted_never_routes_to_openai
test_embedding_restricted_never_openai
```

CI fails if any invariant breaks.

```bash
# Verify live
curl http://localhost:8000/metrics | grep restricted
# restricted_data_cloud_violations_total 0  ✅
```

---

## PII Protection

`PIIMasker` wraps Microsoft Presidio with a custom recognizer for Canadian SIN numbers.

**Mask → Send → Unmask flow:**

```mermaid
flowchart TD
    A(["Prompt received"])
    B["Presidio AnalyzerEngine\ndetect entities in prompt"]
    C["Replace with typed placeholders\n&lt;PERSON_0&gt; · &lt;CREDIT_CARD_0&gt; · &lt;CA_SIN_0&gt;\nstore entity map in job state"]
    D(["Send masked prompt to LLM\nPII never reaches the cloud"])
    E["LLM generates response\n(sees only placeholders)"]
    F["PIIMasker.scan(response)\ndetect any hallucinated PII leakage"]
    G["PIIMasker.unmask(response)\nrestore original entities via entity map"]
    H(["Clean response delivered to client"])

    A --> B --> C --> D --> E --> F --> G --> H
```

**Supported entity types:** `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `CA_SIN`, `IBAN_CODE`, `IP_ADDRESS`, `URL`

---

## RAG Pipeline

```mermaid
flowchart TD
    RI(["POST /api/v1/rag/index"])
    TC["TextChunker\n400 words · 50-word overlap\n→ N overlapping chunks"]
    EF["EmbeddingProviderFactory.get(data_classification)"]
    OE["OllamaEmbeddingProvider\n768-dim · nomic-embed-text\nRESTRICTED / CONFIDENTIAL"]
    OOE["Ollama 768-dim\nor OpenAI 1536-dim\nINTERNAL / PUBLIC"]
    DB[("INSERT INTO document_chunks_768\npgvector · IVFFlat ANN index\nON CONFLICT DO NOTHING")]

    RI --> TC --> EF
    EF -->|"RESTRICTED / CONFIDENTIAL"| OE
    EF -->|"INTERNAL / PUBLIC"| OOE
    OE & OOE --> DB
```

```mermaid
flowchart TD
    RQ(["POST /api/v1/rag/query"])
    EQ["Embed query\nsame provider routing as indexing"]
    ANN["ANN search\nORDER BY embedding ⟺ query_vector LIMIT top_k\nWHERE namespace = ns AND data_class = ANY(allowed_classes)"]
    BC["RAGService.build_context(chunks)\nnumbered source list with similarity scores"]
    OUT(["Context returned to caller"])

    RQ --> EQ --> ANN --> BC --> OUT
```

**Classification-aware retrieval:** a `PUBLIC` query cannot see `INTERNAL` or `RESTRICTED` chunks. `_allowed_classifications()` returns the set of levels ≤ the request's classification.

**Auto-pull:** `OllamaEmbeddingProvider` detects a "model not found" 404 and pulls `nomic-embed-text` automatically on first use (~274MB, one-time).

---

## Observability

### Prometheus Metrics

All metrics exposed at `GET /metrics` (Prometheus text format).

| Metric | Type | Key Labels |
|--------|------|-----------|
| `gateway_requests_total` | Counter | `team_id`, `model_alias`, `provider`, `tier`, `status` |
| `inference_cost_usd_total` | Counter | `team_id`, `model_alias`, `provider`, `tier` |
| `pii_detections_total` | Counter | `entity_type` |
| `restricted_data_cloud_violations_total` | Counter | _(must stay 0)_ |
| `gateway_inference_latency_seconds` | Histogram | `model_alias`, `provider` |
| `provider_health_up` | Gauge | `provider`, `tier` |
| `budget_utilization_ratio` | Gauge | `team_id` |

### Audit Log (TimescaleDB)

Every request appends a row to the `audit_log` hypertable (partitioned by `created_at`).

```sql
SELECT team_id, model_alias, provider, tier, data_class, cost_usd, latency_ms, created_at
FROM audit_log
WHERE created_at > NOW() - INTERVAL '1 hour';
```

### Grafana

Dashboards are pre-provisioned from `grafana/provisioning/`. Available at http://localhost:3001 after `make up`.

---

## Budget Enforcement

`BudgetService` tracks cumulative spend per team and enforces monthly caps with pre-flight checks before any LLM call is made.

```mermaid
flowchart TD
    A(["Request arrives"])
    B["BudgetService.check(team_id, estimated_cost)"]
    C{"Under cap?"}
    D(["HTTP 429\nBudget exceeded\nbefore any LLM cost incurred"])
    E["Proceed to LLM call"]
    F(["Response received"])
    G["BudgetService.record(team_id, actual_cost_usd)"]

    A --> B --> C
    C -->|"Yes"| E --> F --> G
    C -->|"No"| D
```

The `budget_utilization_ratio` Prometheus gauge provides live visibility per team.

---

## Circuit Breaker

`ProviderHealth` tracks failures per provider.

| Setting | Value |
|---------|-------|
| Failure threshold | 3 consecutive failures |
| Circuit open duration | 60 seconds |
| Reset | Half-open (single probe after timeout) |

When a circuit opens, `ModelRouter._select_available_tier()` skips that provider and advances to the next in `FALLBACK_CHAIN`:

```mermaid
flowchart LR
    ANT["Anthropic\nTier 1A"]
    AZ["Azure OpenAI Canada\nTier 1B"]
    OLL["Ollama\nTier 2/3\nfinal fallback — circuit never opens"]

    ANT -->|"circuit open"| AZ
    AZ -->|"circuit open"| OLL
```

Ollama's circuit is never opened — it is always the final fallback.

---

## Async Job Model

Inference runs asynchronously. Clients receive a `job_id` immediately and poll until the job completes.

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway

    C->>G: POST /api/v1/inference
    G-->>C: 202 Accepted { "job_id": "uuid" }

    loop Poll until done
        C->>G: GET /api/v1/jobs/{id}
        alt still running
            G-->>C: { "status": "pending" }
        else completed
            G-->>C: { "status": "completed", "result": "..." }
        else failed
            G-->>C: { "status": "failed", "error": "..." }
        end
    end
```

Both SDKs include `poll_job()` helpers with configurable timeout and exponential backoff.

---

## Config-Driven Model Registry

`config/model_registry.yaml` is the single source of truth for all model IDs and per-token costs. No model identifier appears in routing or provider logic.

```yaml
# config/model_registry.yaml
sonnet:
  tier1_anthropic: "claude-sonnet-4-6"
  tier1_azure:     "claude-sonnet-4-6"
  tier3_ollama:    "qwen2.5:0.5b"
  cost_input_per_mtok:  3.00
  cost_output_per_mtok: 15.00
  context_tokens:  1000000
```

**To upgrade a model:** change one YAML value, run `make build`. Zero code changes required anywhere else.

---

## Scaling Path

| Stage | Description | Code Changes |
|-------|-------------|-------------|
| **Demo** | Single Compose node, CPU, ~150 req/s | — |
| **Production** | Add vLLM GPU tier to Compose; restore `tier2_vllm` registry entries | 0 |
| **Enterprise** | K8s replicas, TimescaleDB read replicas, global LB | 0 |

Aegis is infrastructure-agnostic by design. All scaling is in the infrastructure layer.
