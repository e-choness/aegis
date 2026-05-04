# Technical Specification: Enterprise AI Platform
# Version 2.0 — Updated May 2026

> **What changed in v2**: All model IDs updated. Pricing corrected. `azure_openai` secondary now explicitly specifies Canada region (not US). Polyglot SDK section updated with current Anthropic API model strings. Fallback chain corrected. `EmbeddingProvider` interface replaces hardcoded `OpenAIEmbedding`. Ollama models updated to current 2026 recommendations. Technical tradeoffs documented for all major decisions.

---

## 1. System Overview

### Problem Statement
500+ engineers at a regulated Canadian fintech are using fragmented, ungoverned AI tools (direct API keys, one-off integrations) that create:
- Compliance risk: RESTRICTED customer data reaching US-based LLM providers
- Cost risk: No budget controls, no attribution, runaway spend
- Security risk: No PII scanning, prompt injection undefended
- Quality risk: No evals, no way to detect model quality regressions

### Solution
A centralized AI gateway platform that mediates 100% of AI traffic, enforcing data classification, PII masking, budget controls, and audit logging — while providing polyglot SDKs so engineers can access AI capabilities in their existing tools without managing infrastructure.

---

## 2. Architecture Layers

### Layer 1: Interaction
GitHub/GitLab webhook events, VS Code / JetBrains IDE extensions, Slack bots, CLI tools.

**Integration requirement**: All webhook sources must use HMAC-SHA256 signature verification. Replay attacks prevented via Redis delivery-ID deduplication (24-hour TTL).

### Layer 2: Polyglot SDK Abstraction

```
SDK Interface (all languages expose identical semantics):
  authenticate(sso_token: str) → void
  review_pr(diff_url: str, options: ReviewOptions) → JobId
  query_docs(question: str, context: Context) → Response
  submit_inference(prompt: str, task_type: str) → JobId

Error surface (normalized across providers — callers never see provider errors):
  AuthenticationError (401)
  RateLimitError (429, includes retry-after)
  BudgetExceededError (402)
  DataResidencyError (451)   ← new in v2: returned when RESTRICTED data rejected
  ModelUnavailableError (503)
```

**Tradeoff — 4 SDKs vs. generic HTTP client**:
Generic HTTP: 1 client to maintain. But 500 developers write their own retry logic, auth, and error handling — the fragmented mess the platform was meant to solve.
Polyglot SDKs: 4 clients to maintain. But every engineer gets the same experience, retry logic, and error surface regardless of language. Platform team owns the operational complexity so engineers don't have to.

### Layer 3: AI Gateway (Single Governance Chokepoint)

Every AI call passes through this sequence before reaching any provider:

```
1. AuthN/AuthZ      — SSO token validation (Okta/Azure AD) + OPA RBAC check
2. Data Classifier  — RESTRICTED / CONFIDENTIAL / INTERNAL / PUBLIC
3. PII Masker       — Microsoft Presidio NER (open-source); blocks RESTRICTED, masks CONFIDENTIAL
4. Injection Scan   — LLM Guard prompt safety classifier
5. Budget Check     — Pre-flight cost estimate + team budget validation
6. Model Router     — Cost + capability + classification → ModelConfig
7. Job Enqueue      — Sidekiq (Ruby) / Celery (Python); webhook returns HTTP 202
8. Provider Call    — ProviderFactory.get(config.provider).complete(request)
9. Output Validate  — Scan response for secrets/PII leakage before returning
10. Unmask PII      — Restore masked values in response where appropriate
11. Audit Log       — TimescaleDB (hot) → S3 Object Lock (cold, 7-year retention)
12. Cost Record     — CostTracker.record(team_id, cost, model_alias, provider, tier)
```

**Tradeoff — Monolithic gateway vs. sidecar per service**:
Monolithic gateway (implemented): Single deployment, easier to reason about, single audit log.
Sidecar/service mesh: More resilient (no single point), but PII masking and audit logging become distributed — harder to guarantee 100% coverage. Central governance wins for compliance.

### Layer 4: Provider Tiers

```yaml
Tier 1 — Cloud (CONFIDENTIAL and INTERNAL data only):
  Primary:   Anthropic Claude (claude-haiku-4-5-20251001 / claude-sonnet-4-6 / claude-opus-4-7)
  Secondary: Azure OpenAI Canada region (same model IDs via AI Foundry)
  Note: US-based OpenAI is NOT a valid secondary. Azure Canada region is PIPEDA-compliant.

Tier 2 — Self-hosted (all classifications including RESTRICTED):
  Runtime:    vLLM on Kubernetes
  Models:     llama3.3:70b-instruct-q4_K_M (general), devstral-small:24b (coding)
  Embeddings: bge-m3 (768-dim, multilingual)
  Hardware:   Minimum 2× NVIDIA A100 80GB (43GB VRAM for 70B at Q4_K_M)

Tier 3 — Offline (all classifications; no network required):
  Runtime:    Ollama (localhost:11434)
  Models:
    General:    qwen2.5:7b (6GB VRAM), llama3.2:8b (6GB VRAM)
    Coding:     qwen2.5-coder:32b (22GB), codestral:22b (FIM support)
    Reasoning:  deepseek-r1:14b (chain-of-thought debugging)
    Lightweight: qwen2.5:3b (CPU-viable, minimal VRAM)
    Embeddings: nomic-embed-text (274MB, 768-dim, outperforms ada-002 on retrieval)
```

**Tradeoff — Ollama vs. llama.cpp directly**:
llama.cpp: More control, slightly faster, no Ollama overhead.
Ollama (chosen): Model management (`ollama pull`), OpenAI-compatible API, hot-swap between models, no code changes when switching models. The simplicity wins for developer machines and CI.

---

## 3. Current Model Pricing (May 2026)

### Anthropic Claude — Active Models

| Alias | Model ID | Input $/MTok | Output $/MTok | Context | Notes |
|---|---|---|---|---|---|
| `haiku` | `claude-haiku-4-5-20251001` | $1.00 | $5.00 | 200K | Up from $0.25/$1.25 (Haiku 3, retired) |
| `sonnet` | `claude-sonnet-4-6` | $3.00 | $15.00 | 1M | Unchanged; recommended default |
| `opus` | `claude-opus-4-7` | $5.00 | $25.00 | 1M | Down from $15/$75; new tokenizer +35% |

**Opus 4.7 Tokenizer Note**: Per-token rate is unchanged from Opus 4.6, but the new tokenizer generates up to 35% more tokens for the same input text. Effective cost per request can increase by up to 35%. Apply 1.35x safety multiplier in budget pre-flight checks for any `opus` alias call.

**Cost optimizers**:
- Prompt caching: Up to 90% savings on repeated system prompts (cache_control: ephemeral)
- Batch API: 50% discount for async workloads (nightly eval runs, documentation indexing)
- Prompt caching + Batch stack: Effective cost as low as 5% of standard rate

### On-Prem / Offline Tiers

| Tier | Provider | Cost Model | Quality vs. Cloud |
|---|---|---|---|
| Tier 2 | vLLM (Llama 3.3 70B) | ~$0.10/MTok amortized GPU | ~70-80% of Sonnet quality on code |
| Tier 3 | Ollama (qwen2.5-coder:32b) | $0.00 (electricity only) | ~60-70% of Sonnet on code tasks |

---

## 4. Provider-Agnostic Design

### Interface Hierarchy

```
LLMProvider (ABC)
├── AnthropicProvider    — tier 1, cloud
├── AzureOpenAIProvider  — tier 1, Canada region
├── VLLMProvider         — tier 2, on-prem
└── OllamaProvider       — tier 3, offline

EmbeddingProvider (ABC)
├── OpenAIEmbeddingProvider  — tier 1, PUBLIC/INTERNAL only; 1536-dim
├── VLLMEmbeddingProvider    — tier 2, all classifications; 768-dim BGE-M3
└── OllamaEmbeddingProvider  — tier 3, all classifications; 768-dim nomic-embed-text

HealthChecker (ABC)
└── DefaultHealthChecker     — polls each provider's health endpoint every 30s

CostCalculator (ABC)
├── AnthropicCostCalculator  — applies 1.35x margin for opus alias (Opus 4.7 tokenizer)
├── VLLMCostCalculator       — amortized GPU cost ($0.10/MTok estimate)
└── OllamaCostCalculator     — $0.00 (tracked for utilization, not billing)
```

### EmbeddingProvider Interface (Fixes Hardcoded OpenAIEmbedding)

```python
# Previously (WRONG — from original codebase):
from llama_index.embeddings import OpenAIEmbedding
embedding = OpenAIEmbedding(model="text-embedding-3-small")
# Problems: PIPEDA violation for RESTRICTED data; no fallback; no offline

# Now (CORRECT):
from intelligence.providers.embeddings.factory import EmbeddingProviderFactory

embedding_provider = EmbeddingProviderFactory.get(
    data_classification=DataClassifier().classify(document_text),
    health_checker=health_checker,
)
vectors = await embedding_provider.embed(chunks)

# EmbeddingProviderFactory routing:
# RESTRICTED → VLLMEmbeddingProvider (tier 2) else OllamaEmbeddingProvider (tier 3)
# CONFIDENTIAL → VLLMEmbeddingProvider else OpenAIEmbeddingProvider else Ollama
# INTERNAL → any available, preferring VLLMEmbeddingProvider
# PUBLIC → OpenAIEmbeddingProvider else Ollama
```

**Dimension consistency rule**: All indexes that may store RESTRICTED or CONFIDENTIAL data use 768-dim vectors (BGE-M3 / nomic-embed-text). A separate 1536-dim index may be maintained for PUBLIC data using OpenAI embeddings. Never mix dimensions within a single index.

---

## 5. Epics & Stories

### Epic 1: Core Gateway Foundation

**Story 1.1: Authentication and Authorization**
```
As a platform engineer,
I want SSO-based authentication with RBAC enforcement
So that every AI call is traceable to a verified identity with appropriate permissions.

Acceptance Criteria:
- [ ] Okta/Azure AD JWT validation on every gateway request
- [ ] OPA policy engine: role-to-model-alias mapping (e.g., senior_dev → opus allowed)
- [ ] Service-to-service auth via mTLS
- [ ] Auth failure → HTTP 401 with trace ID
- [ ] Token refresh handled transparently in SDK
```

**Story 1.2: Data Classification and Routing**
```
As a compliance officer,
I want RESTRICTED data to never reach cloud providers
So that we cannot have a PIPEDA violation regardless of developer behavior.

Acceptance Criteria:
- [ ] DataClassifier.classify() runs before ModelRouter.route() on every request
- [ ] RESTRICTED classification → ModelConfig.tier >= 2 always; verified by unit test
- [ ] Audit log records data_class field for every call
- [ ] Compliance report query: SELECT COUNT(*) WHERE data_class='RESTRICTED' AND tier=1 always returns 0
```

**Story 1.3: Smart Model Router**
```
As a developer,
I want the platform to automatically select the right model
So that I don't pay Opus prices for commit message summaries.

Acceptance Criteria:
- [ ] commit_summary task → haiku alias ($1/MTok input)
- [ ] pr_review task → sonnet alias ($3/MTok input)
- [ ] security_audit + high complexity → opus alias ($5/MTok input)
- [ ] Budget-aware degradation: opus → sonnet when team budget < $1.00 remaining
- [ ] Opus 4.7: 1.35x safety multiplier in estimate_cost_usd()
- [ ] All routing decisions logged to metrics (model_alias, provider, tier)
```

### Epic 2: Provider Integration

**Story 2.1: Anthropic Provider**
```
Acceptance Criteria:
- [ ] Uses claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-7 only (active models)
- [ ] No retired model IDs appear anywhere in code or config
- [ ] API key fetched from Vault at runtime (never from os.environ)
- [ ] Prompt caching: cache_control: {type: "ephemeral"} on system prompts
- [ ] Health check pings haiku model every 30s; circuit breaker opens on 3 failures
```

**Story 2.2: Azure OpenAI Canada Provider**
```
Acceptance Criteria:
- [ ] Endpoint: Canada region only (e.g., canadaeast.api.cognitive.microsoft.com)
- [ ] Not US OpenAI endpoint (api.openai.com) — PIPEDA non-compliance
- [ ] Same LLMProvider interface as AnthropicProvider — zero application code changes on failover
- [ ] Automatic failover when Anthropic circuit breaker opens
```

**Story 2.3: vLLM Provider (Tier 2)**
```
Acceptance Criteria:
- [ ] Serves llama3.3:70b-instruct-q4_K_M for sonnet alias
- [ ] Serves devstral-small:24b-q5_K_M for opus alias
- [ ] RESTRICTED data confirmed to route here (FR-4 acceptance criteria)
- [ ] BGE-M3 embedding service via VLLMEmbeddingProvider
- [ ] Health endpoint at /health; 30s ping
```

**Story 2.4: Ollama Provider (Tier 3 — Offline)**
```
Acceptance Criteria:
- [ ] Serves qwen2.5:7b for haiku alias
- [ ] Serves qwen2.5-coder:32b for sonnet alias (falls back to qwen2.5:7b if <22GB VRAM)
- [ ] Serves devstral-small:24b for opus alias (falls back to sonnet alias if <16GB VRAM)
- [ ] nomic-embed-text for OllamaEmbeddingProvider (pull: ollama pull nomic-embed-text)
- [ ] Full PR review functionality with zero network calls (FR-5)
- [ ] Graceful degradation: if large model not pulled, fall back to next smaller model
```

### Epic 3: Polyglot SDK Ecosystem

**Story 3.1: Ruby SDK**
```ruby
# Usage
client = AIPlatform::Client.new(sso_token: token)
job_id = client.review_pr(diff_url: url, classification: :internal)
result  = client.poll_job(job_id, timeout: 90)

# Error handling
rescue AIPlatform::RateLimitError => e
  retry after: e.retry_after
rescue AIPlatform::DataResidencyError => e
  # RESTRICTED data blocked — not a bug, inform developer
```

**Story 3.2: Python SDK**
```python
# Usage
client = AIPlatformClient(sso_token=token)
job_id = await client.review_pr(diff_url=url)
result = await client.poll_job(job_id, timeout=90)

# Async context manager support
async with AIPlatformClient(sso_token=token) as client:
    result = await client.query_docs("What is our auth pattern?")
```

**Story 3.3: TypeScript SDK**
```typescript
const client = new AIPlatformClient({ ssoToken: token });
const jobId  = await client.reviewPR({ diffUrl: url });
const result = await client.pollJob(jobId, { timeout: 90_000 });
```

### Epic 4: Observability

**Story 4.1: Distributed Tracing**
```
Acceptance Criteria:
- [ ] OpenTelemetry spans on every request: SDK → gateway → job queue → provider → response
- [ ] Span attributes: user_id, team_id, model_alias, provider, tier, data_class, cost_usd, cache_hit
- [ ] Export to Jaeger / Datadog
- [ ] Trace ID propagated in all error messages (enables support lookups)
```

**Story 4.2: Cost Attribution**
```
Acceptance Criteria:
- [ ] Every inference call writes to inference_audit_log (team_id, model_alias, provider, tier, cost_usd)
- [ ] Real-time dashboard: cost per team per day, per model alias, per tier
- [ ] Budget utilization alerts: Slack at 70%, PagerDuty at 100%
- [ ] Monthly cost report: per-team breakdown with routing efficiency metrics
```

### Epic 5: Evaluation Pipeline

**Story 5.1: Golden Dataset and Automated Evals**
```
Acceptance Criteria:
- [ ] 100 labeled PR diffs covering: security (SQL injection, auth bypass, SSRF), 
      performance (N+1 queries, memory leaks), style, and false-positive cases
- [ ] Evals run automatically on every model alias update in model_registry.yaml
- [ ] Quality gate: new alias must achieve F1 ≥ (current_baseline × 1.05) to deploy
- [ ] Batch API used for eval runs (50% cost savings)
- [ ] Auto-rollback: if error rate increases >10% within 1 hour of alias update, revert
```

---

## 6. Technology Choices

| Component | Choice | Rationale | Tradeoff |
|---|---|---|---|
| **LLM Gateway** | LiteLLM + Kong/Tyk | Open-source; supports 100+ providers; self-hosted; provider abstraction | Small maintainer team; escape hatch: Kong + Lua plugin |
| **PII Masking** | Microsoft Presidio | Open-source; supports Canadian SIN, credit cards; customizable | Regex-based by default; add ML NER model for obfuscated PII in Phase 3 |
| **Prompt Injection** | LLM Guard | Open-source; production-ready; pluggable classifiers | Adds ~15ms latency; false positive rate requires tuning |
| **Async Queue (Ruby)** | Sidekiq | Battle-tested; excellent monitoring; Redis-backed | Ruby-only; Celery needed for Python workers |
| **Async Queue (Python)** | Celery | Mature; supports multiple brokers; async-native | Two queue systems in polyglot env; evaluate Temporal for Phase 4 |
| **Vector DB** | pgvector (default) | No new infrastructure; 768-dim indexes; SQL queries | Scale limit ~1M vectors; add Qdrant for Phase 4 scale |
| **Embedding (cloud)** | OpenAI text-embedding-3-small | 1536-dim; simple; PUBLIC data only | US-based; cannot use for RESTRICTED/CONFIDENTIAL |
| **Embedding (on-prem)** | BGE-M3 via vLLM | 768-dim; multilingual (supports French); all classifications | Requires GPU server |
| **Embedding (offline)** | nomic-embed-text via Ollama | 768-dim; 274MB; beats ada-002 on retrieval benchmarks | Not a managed service; must pre-pull model |
| **Secrets** | HashiCorp Vault | Rotation; runtime injection; open-source option | Operational overhead; AWS Secrets Manager acceptable alternative |
| **Observability** | OpenTelemetry + Prometheus + Grafana | Standard; cloud-agnostic; open-source | Jaeger for traces; Datadog as paid alternative |

---

## 7. Implementation Sequence

```
Phase 1 (Months 1-3): Governance foundation
  - Core gateway (Rails API)
  - Anthropic provider (AnthropicProvider implements LLMProvider)
  - AuthN/AuthZ (Okta + OPA)
  - Data classifier + hard routing rule for RESTRICTED
  - Ruby SDK (gem)
  - Sidekiq async job queue
  - Basic audit logging (TimescaleDB)

Phase 2 (Months 4-6): Full governance + polyglot
  - PII masking (Presidio)
  - Prompt injection defense (LLM Guard)
  - Budget enforcement (pre-flight + real-time)
  - Azure OpenAI Canada provider (AzureOpenAIProvider implements LLMProvider)
  - Observability (OpenTelemetry + Prometheus + Grafana)
  - Python + TypeScript + Kotlin SDKs
  - IDE extensions (VS Code)

Phase 3 (Months 7-9): Self-hosted + RAG
  - vLLM deployment on-prem (GPU server required)
  - VLLMProvider + VLLMEmbeddingProvider
  - RAG pipeline with EmbeddingProviderFactory (replaces OpenAIEmbedding hardcoding)
  - pgvector index (768-dim canonical)
  - Evals pipeline + golden dataset

Phase 4 (Months 10-12): Offline + resilience
  - OllamaProvider + OllamaEmbeddingProvider
  - Ollama model pre-pull: qwen2.5:7b, qwen2.5-coder:32b, nomic-embed-text
  - Multi-region gateway deployment
  - Chaos engineering (quarterly DR drills)
  - A/B testing framework for model upgrades
  - GA launch: 500+ engineers
```

---

## 8. Testing Strategy

### Unit Tests (Per-Service, Isolated)
```python
def test_restricted_routing_invariant():
    """RESTRICTED data must NEVER reach tier 1 providers."""
    router = ModelRouter(health_checker=AlwaysHealthyMock())
    config = router.route("any_task", "any_complexity", "RESTRICTED")
    assert config.tier >= 2
    assert config.provider not in ("anthropic", "azure_openai")

def test_embedding_factory_restricted_never_openai():
    provider = EmbeddingProviderFactory.get("RESTRICTED", AlwaysHealthyMock())
    assert not isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.dimensions == 768

def test_opus_cost_estimate_tokenizer_margin():
    provider = AnthropicProvider.__new__(AnthropicProvider)
    cost = provider.estimate_cost_usd(1_000_000, 200_000, "opus")
    # Expected: (1M * $5 + 200K * $25) * 1.35 / 1M = $13.50
    assert abs(cost - 13.50) < 0.01

def test_retired_model_not_in_registry():
    registry = yaml.safe_load(open("gateway/config/model_registry.yaml"))
    retired = ["claude-3-haiku-20240307", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
    for model_id in retired:
        assert model_id not in str(registry), f"Retired model ID found: {model_id}"
```

### Integration Tests
```python
def test_pr_review_end_to_end_async():
    """GitHub webhook → 202 response → job enqueued → review posted."""
    response = client.post("/webhooks/github", json=fake_pr_event())
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    # Poll until complete (max 90s)
    result = wait_for_job(job_id, timeout=90)
    assert result.status == "completed"
    assert result.review.comments  # At least one comment posted

def test_budget_enforcement_hard_stop():
    team = create_team(budget=100.00, spent=100.01)
    response = client.post("/api/v1/inference", json={"team_id": team.id, "prompt": "test"})
    assert response.status_code == 402
    assert "budget" in response.json()["error"].lower()
```

### Load Tests (Locust)
```python
class GatewayUser(HttpUser):
    @task
    def submit_pr_review(self):
        self.client.post("/api/v1/inference", json={
            "task_type": "pr_review",
            "prompt": fake_diff(),
            "team_id": "eng-platform"
        })

# Target: 200 req/minute sustained for 4 hours
# Acceptance: p99 latency <500ms (gateway overhead only), 0% error rate
```

### Chaos Engineering (Quarterly)
```bash
# Simulate Anthropic outage
kubectl exec -n gateway deployment/circuit-breaker -- force-open --provider=anthropic

# Verify automatic failover to Azure Canada
./verify_failover.sh --expect-provider=azure_openai --timeout=120

# Simulate all cloud outages
for provider in anthropic azure_openai; do
  kubectl exec -n gateway deployment/circuit-breaker -- force-open --provider=$provider
done

# Verify fallback to vLLM
./verify_failover.sh --expect-tier=2

# Verify RESTRICTED data still on-prem (not affected by cloud outage chaos)
./verify_restricted_routing.sh --expect-tier=2
```
