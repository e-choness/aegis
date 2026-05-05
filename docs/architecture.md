# Architecture

## Simplified Single-Container Design (Solo Builder)

Aegis is inspired by OpenClaude's config-driven approach: provider-agnostic, container-native, and zero host dependencies. Everything runs in Docker.

### Key Differences from Multi-Tier Enterprise

- **No GPU required** — removed vLLM Tier 2 (which needed A100s)
- **Ollama is the universal local tier** — serves RESTRICTED data, offline mode, and cost-free inference
- **Three-tier fallback** — Anthropic → Azure OpenAI Canada → Ollama
- **Simplified ops** — one Docker Compose, no Kubernetes, no GPU cluster

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client (SDK / CLI)                                                  │
└───────────────────┬─────────────────────────────────────────────────┘
                    │ POST /api/v1/inference
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Gateway (src/gateway/main.py)                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  InferenceService._run() — asyncio.create_task             │   │
│  │                                                             │   │
│  │  1. DataClassifier.classify()        <1ms regex             │   │
│  │  2. PIIMasker.mask()                 Presidio               │   │
│  │  3. ModelRouter.route()              rules-based            │   │
│  │  4. BudgetService.check()            pre-flight             │   │
│  │  5. ProviderFactory.get().complete() → LLM call             │   │
│  │  6. scan_output()                    leakage check          │   │
│  │  7. unmask()                         restore entities       │   │
│  │  8. BudgetService.record_spend()     cost accounting        │   │
│  │  9. AuditLogger.log()                TimescaleDB            │   │
│  │  10. Prometheus counters                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────┬───────────┬────────────────────────────────┘
                        │           │
      ┌─────────────────▼─────────┐ ┌─▼────────────────────┐
      │  Anthropic (Tier 1A)       │ │  Azure OpenAI (Tier1B)│
      │  claude-sonnet-4-6, etc.   │ │  Canada region        │
      └─────────────────┬─────────┘ └─────────┬────────────┘
                        │                       │
            ┌───────────▼───────────┐  ┌───────▼──────┐
            │  Ollama (Tier 2/3)     │  │  TimescaleDB  │
            │  qwen2.5, sonnet, opus │  │  (audit log)  │
            │  ALL data classes      │  └───────────────┘
            └────────────────────────┘
```

## Data Classification

`DataClassifier.classify()` uses regex only — <1ms, deterministic, auditable.

| Level | Triggers | Example |
|-------|----------|---------|
| RESTRICTED | Canadian SIN, credit card, account_number keyword | `123-456-789` |
| CONFIDENTIAL | Internal email, api_key keyword, Bearer token | `Bearer eyJ...` |
| INTERNAL | Everything else | Business text |
| PUBLIC | Caller-specified | Public docs |

## PIPEDA Hard Invariant

**RESTRICTED data never reaches cloud providers.** This is enforced in `src/gateway/services/router.py`:

```python
if data_classification == DataClassification.RESTRICTED:
    return self._build_config("local", "ollama", "tier3_ollama", 3)
```

The compliance view in TimescaleDB must always return 0 rows:
```sql
SELECT COUNT(*) FROM inference_audit_log 
WHERE data_class = 'RESTRICTED' AND tier = 1;  -- Must be 0
```

The `restricted_data_cloud_violations_total` Prometheus counter is monitored for this.

## Provider Selection

### Fallback Chain

```
Anthropic (1A) → Azure OpenAI Canada (1B) → Ollama (2/3)
```

- Anthropic: Primary, highest quality
- Azure OpenAI Canada: PIPEDA-safe Canadian fallback  
- Ollama: Local/offline, serves RESTRICTED data, always available

### Routing Rules (priority order)

1. **RESTRICTED** → force Ollama, regardless of task or budget
2. **Task type** → `commit_summary`→haiku, `pr_review`→sonnet, `security_audit`→opus
3. **Complexity** → `security_audit` + high → always opus
4. **Budget** → opus with <$1.00 remaining → degrade to sonnet

Circuit breaker: 3 failures in 60s → mark unhealthy, try next in chain.

## Model Registry

`config/model_registry.yaml` is the SINGLE source of truth. Never hardcode model IDs.

```yaml
sonnet:
  tier1_anthropic: "claude-sonnet-4-6"
  tier1_azure:     "claude-sonnet-4-6"
  tier3_ollama:    "qwen2.5-coder:32b"
  cost_input_per_mtok:  3.00
  cost_output_per_mtok: 15.00
```

**Opus 4.7 tokenizer note**: New tokenizer generates ~35% more tokens. Cost estimates use 1.35× safety margin.

## PII Masking

`PIIMasker` uses Microsoft Presidio + custom Canadian SIN recognizer. Masks right-to-left to preserve offsets, then restores in the LLM response.

## Provider-Agnostic Design

Like OpenClaude, all provider access goes through abstract interfaces:

```python
from intelligence.providers.factory import ProviderFactory
from intelligence.providers.embeddings.factory import EmbeddingProviderFactory

# LLM calls
provider = ProviderFactory.get("anthropic")
response = await provider.complete(request)

# Embeddings (classification-driven routing)
embedder = EmbeddingProviderFactory.get(classification, health_checker)
vectors = await embedder.embed(chunks)
```

**Benefits:**
- Swap providers without code changes
- Mock easily for testing
- Compliance enforced as code invariant

## Databases

| Database | Port | Purpose |
|----------|------|---------|
| TimescaleDB | 5432 | Inference audit log (7-year retention) |
| pgvector | 5433 | RAG document vectors (768-dim canonical) |

⚠️ **768-dim vs 1536-dim**: Can't mix in one index. Sensitive data → 768-dim (Ollama/BGE). Public data → 1536-dim (OpenAI) in separate index.

## Observability

- **Prometheus** (`/metrics`): Per-team costs, PII detections, circuit breaker state
- **Grafana** (port 3001): Cost dashboards, health, latency
- **Audit log**: TimescaleDB → queryable by team/model/provider

Critical alerts:
- `restricted_data_cloud_violations_total > 0` — COMPLIANCE BREACH
- `provider_health_up{provider="anthropic"} == 0` — Primary down
- `budget_utilization_ratio > 0.90` — Budget near cap

## Testing

```bash
make test      # All tests in Docker (no host installs)
make test-py   # Gateway tests
```

Tests verify:
- RESTRICTED data never reaches cloud
- Ollama fallback works when cloud is down
- Cost estimates include Opus tokenizer margin
- PII masking/unmasking correctness
- Circuit breaker behavior
