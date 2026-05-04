# Solution Architect Design Document
# Enterprise AI Platform for Developer Productivity
# Version 2.0 — Updated May 2026

> **What changed in v2**: Model IDs updated to current active versions. Pricing corrected ($0.25 Haiku 3 → $1.00 Haiku 4.5; $15 Opus 4.1 → $5 Opus 4.7). Opus 4.7 tokenizer inflation documented. Provider-agnostic interface design (`LLMProvider`, `EmbeddingProvider`) replaces hardcoded provider calls. Fallback chain conflict resolved: Azure OpenAI Canada (not US OpenAI) as secondary. Ollama fully specified as Tier 3. Model routing decision matrix clarified and expanded. Technical tradeoffs documented throughout.

---

## 1. Strategic Architecture Goals

| Goal | Mechanism | Tradeoff |
|---|---|---|
| **Governance** | Gateway as single chokepoint | Single point of failure risk → mitigated by HA gateway |
| **Cost Control** | Track spend per team, per alias, per tier | TimescaleDB adds infrastructure overhead → worth it for attribution |
| **Reliability** | Four-tier fallback chain | More providers = more ops complexity → worth it for 99.9% target |
| **Compliance** | Data classification enforced as code invariant | Hard routing limits flexibility → intentional |
| **Agnostic design** | `LLMProvider` + `EmbeddingProvider` interfaces | More abstraction layers → worth it for provider independence |

---

## 2. Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: INTERACTION                                           │
│  GitHub/GitLab webhooks → IDE plugins → Slack bots → CLI       │
└───────────────────────────────┬─────────────────────────────────┘
                                │ (async via job queue)
┌───────────────────────────────▼─────────────────────────────────┐
│  LAYER 2: POLYGLOT SDK                                          │
│  Ruby gem │ Python pkg │ TypeScript npm │ Kotlin maven          │
│  Depends on LLMProvider interface — never on concrete classes   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  LAYER 3: AI GATEWAY & GOVERNANCE (Kong/Tyk orchestrated)       │
│                                                                 │
│  AuthN/AuthZ  → DataClassifier → PIIMasker → InjectionDefense  │
│       │                                                         │
│  ModelAliasRegistry → ModelRouter → BudgetEnforcer             │
│       │                                                         │
│  CostTracker → AuditLogger → RateLimiter                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  LAYER 4: PROVIDER TIERS (resolved by router, not by app code)  │
│                                                                 │
│  Tier 1 (Cloud):     Anthropic │ Azure OpenAI Canada            │
│  Tier 2 (On-prem):   vLLM on Kubernetes (Llama 3.3 / Devstral)│
│  Tier 3 (Offline):   Ollama (qwen2.5, nomic-embed-text)        │
│                                                                 │
│  RESTRICTED data: Tier 2/3 only (enforced in ModelRouter code) │
└─────────────────────────────────────────────────────────────────┘
```

**Rationale for Gateway as Single Chokepoint**: All governance — PII masking, data classification, rate limiting, cost tracking, prompt injection defense — is implemented once at the gateway. Without the chokepoint, each team must implement these individually (they won't), and there is no audit trail. The tradeoff is a single point of failure, mitigated by multi-region gateway deployment, circuit breakers, and the fact that each tier of the provider chain operates independently of the gateway's HA configuration.

---

## 3. Data Classification and Routing

### Classification Rules

```python
class DataClassifier:
    """
    Runs on every prompt before routing. Classification determines eligible provider tiers.

    TRADEOFF — Speed vs. Coverage:
    Current: Regex-only, <1ms, auditable, zero false negatives on known patterns.
    Future (Phase 3): Add ML classifier as second pass to catch obfuscated PII.
    The ML pass adds 20-50ms latency but catches patterns like "j0hn[dot]d0e@..."
    """

    PATTERNS = {
        "RESTRICTED": [
            r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",     # Canadian SIN
            r"\b(?:\d{4}[-\s]?){4}\b",                # Credit card numbers
            r"\baccount[_-]?number\b",                 # Account reference
            r"\b\d{9,12}\b",                           # Generic account number pattern
        ],
        "CONFIDENTIAL": [
            r"[a-zA-Z0-9._%+-]+@(?:wealthsimple|company)\.com",  # Internal email
            r"\bapi[_-]?key\b",
            r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",        # JWT/bearer tokens
        ],
    }

    def classify(self, text: str) -> str:
        for level in ("RESTRICTED", "CONFIDENTIAL"):
            if any(re.search(p, text, re.I) for p in self.PATTERNS[level]):
                return level
        return "INTERNAL"
```

### Routing Decision Matrix

```python
class ModelRouter:
    """
    Maps task type + complexity + data classification + budget → ModelConfig.

    TRADEOFF — Rules-based vs. ML routing:
    Rules-based (implemented): Deterministic, auditable, testable.
    A bug in a rules-based router is immediately visible in code.
    A bug in an ML router silently routes RESTRICTED data to cloud → PIPEDA violation.
    Rules-based is the only acceptable choice for compliance-critical routing.
    ML routing for cost optimization (not classification) is appropriate for Phase 4.
    """

    # Pricing reference (May 2026) — single source of truth in model_registry.yaml
    # haiku:  $1.00/$5.00 per MTok (input/output)
    # sonnet: $3.00/$15.00 per MTok — 1M context window at standard pricing
    # opus:   $5.00/$25.00 per MTok — NOTE: 1.35x tokenizer safety multiplier for Opus 4.7

    TASK_ALIAS_MAP = {
        # Haiku ($1/MTok input): Use aggressively for simple, high-volume tasks
        "commit_summary":     "haiku",
        "simple_qa":          "haiku",
        "routing":            "haiku",
        "classification":     "haiku",

        # Sonnet ($3/MTok): Default for most engineering tasks
        "pr_review":          "sonnet",    # Default; may escalate to opus on security PRs
        "rag_response":       "sonnet",
        "code_explanation":   "sonnet",
        "documentation":      "sonnet",
        "deployment_check":   "sonnet",

        # Opus ($5/MTok + 1.35x tokenizer margin): Only when genuinely needed
        "security_audit":     "opus",      # High-stakes, complex reasoning required
        "architecture_review": "opus",     # Large context, multi-file analysis
        "multi_file_refactor": "opus",     # Long context + high instruction complexity
    }

    FALLBACK_CHAIN = [
        ("anthropic",    "tier1_anthropic"),
        ("azure_openai", "tier1_azure"),      # Azure OpenAI Canada — PIPEDA-safe secondary
        ("vllm",         "tier2_vllm"),
        ("ollama",       "tier3_ollama"),     # Always available, no network required
    ]

    def route(self, task_type: str, complexity: str, data_classification: str,
              budget_remaining_usd: float = float("inf")) -> ModelConfig:

        # RULE 1: RESTRICTED data never reaches cloud — hard invariant
        if data_classification == "RESTRICTED":
            return self._select_onprem("local")

        # RULE 2: Select alias based on task type
        alias = self.TASK_ALIAS_MAP.get(task_type, "sonnet")

        # RULE 3: Escalate to opus for high-complexity tasks
        if complexity == "high" and alias == "sonnet" and task_type in ("security_audit",):
            alias = "opus"

        # RULE 4: Budget-aware degradation
        if alias == "opus" and budget_remaining_usd < 1.00:
            alias = "sonnet"

        return self._select_tier(alias)
```

---

## 4. Current Model Registry

### Active Models (May 2026)

All model IDs below are confirmed active as of May 2026. Calls to retired IDs return HTTP 404.

```yaml
# gateway/config/model_registry.yaml

haiku:
  tier1_anthropic: "claude-haiku-4-5-20251001"
  tier1_azure:     "claude-haiku-4-5-20251001"
  tier2_vllm:      "llama3.2:8b-instruct-q5_K_M"
  tier3_ollama:    "qwen2.5:7b"
  cost_input_per_mtok:  1.00    # Was $0.25 for retired Haiku 3 (claude-3-haiku-20240307)
  cost_output_per_mtok: 5.00    # Was $1.25

sonnet:
  tier1_anthropic: "claude-sonnet-4-6"
  tier1_azure:     "claude-sonnet-4-6"
  tier2_vllm:      "llama3.3:70b-instruct-q4_K_M"
  tier3_ollama:    "qwen2.5-coder:32b"
  cost_input_per_mtok:  3.00    # Unchanged across 4 generations
  cost_output_per_mtok: 15.00
  context_tokens:  1000000      # 1M context at standard pricing, no surcharge

opus:
  tier1_anthropic: "claude-opus-4-7"      # Active flagship (released Apr 2026)
  tier1_azure:     "claude-opus-4-6"      # 4.7 pending Azure AI Foundry availability
  tier2_vllm:      "devstral-small:24b-q5_K_M"
  tier3_ollama:    "devstral-small:24b-q4_K_M"
  cost_input_per_mtok:  5.00    # Was $15 for retired Opus 4.1 — 67% reduction
  cost_output_per_mtok: 25.00   # Was $75
  tokenizer_margin: 1.35        # Opus 4.7 new tokenizer: up to 35% more tokens vs 4.6
  context_tokens:  1000000

local:
  tier2_vllm:   "llama3.3:70b-instruct-q4_K_M"
  tier3_ollama: "llama3.2:8b-instruct-q5_K_M"

embeddings:
  tier1_openai: "text-embedding-3-small"    # 1536-dim; INTERNAL/PUBLIC only
  tier2_vllm:   "bge-m3"                    # 768-dim; all classifications
  tier3_ollama: "nomic-embed-text"          # 768-dim; 274MB; standard local RAG
```

### Retired Model IDs (DO NOT USE — Will Return HTTP 404)

| Retired ID | Retired Date | Use Instead |
|---|---|---|
| `claude-3-haiku-20240307` | March 2026 | `claude-haiku-4-5-20251001` |
| `claude-3-5-sonnet-20240620` | Retired 2025 | `claude-sonnet-4-6` |
| `claude-3-5-sonnet-20241022` | Retired 2025 | `claude-sonnet-4-6` |
| `claude-3-opus-20240229` | Retired 2025 | `claude-opus-4-7` |
| `claude-opus-4-20250514` | Deprecated (retiring Jun 2026) | `claude-opus-4-7` |
| `claude-sonnet-4-20250514` | Deprecated (retiring Jun 2026) | `claude-sonnet-4-6` |

---

## 5. Provider-Agnostic Interface Design

### Why Interfaces Are Non-Negotiable

**Problem with direct implementation**:
```python
# Before (WRONG — directly coupling to Anthropic)
from llama_index.embeddings import OpenAIEmbedding
embedding = OpenAIEmbedding(model="text-embedding-3-small")
vectors = embedding.embed(chunks)
```
This breaks three ways:
1. RESTRICTED data goes to OpenAI → PIPEDA violation
2. OpenAI outage → RAG pipeline down (no fallback)
3. Offline mode → impossible

**After (CORRECT — interface-driven)**:
```python
# All embedding access through factory
embedding_provider = EmbeddingProviderFactory.get(
    data_classification=classification,
    health_checker=health_checker,
)
vectors = await embedding_provider.embed(chunks)
# Returns correct provider based on: RESTRICTED→vLLM/Ollama; INTERNAL→any; health
```

### Gateway Request Flow

```
Developer Request (any language via SDK)
  ↓
1. AUTHENTICATE: SSO token validated, RBAC checked
   ↓
2. CLASSIFY: DataClassifier.classify(prompt) → "RESTRICTED|CONFIDENTIAL|INTERNAL|PUBLIC"
   ↓
3. MASK PII: Presidio.sanitize(prompt) → (sanitized_text, mask_map)
   ↓
4. INJECTION CHECK: LLMGuard.scan(sanitized_text) → pass/block
   ↓
5. BUDGET CHECK: BudgetService.check(team_id) → ok/reject
   ↓
6. ROUTE: ModelRouter.route(task_type, complexity, classification, budget) → ModelConfig
   ↓
7. COST ESTIMATE: provider.estimate_cost_usd(tokens, alias) → float
   ↓
8. ENQUEUE: InferenceJob.perform_async(model_config, sanitized_text)
   → Return HTTP 202 {"job_id": "..."}
   ↓
   [Worker picks up job]
   ↓
9. CALL PROVIDER: ProviderFactory.get(model_config.provider).complete(request)
   ↓
10. UNMASK: PIIMasker.unmask(response, mask_map) → original_response
    ↓
11. VALIDATE OUTPUT: Check response for secrets/PII leakage
    ↓
12. LOG: AuditLog.create(user_id, team_id, model_alias, provider, tier, cost, trace_id)
    ↓
13. RECORD COST: CostTracker.record(team_id, cost_usd)
    ↓
14. DELIVER: Post result to GitHub / return to SDK caller
```

---

## 6. Observability Architecture

### Distributed Tracing

Every request gets an OpenTelemetry trace spanning all layers:

```python
# Example trace for a PR review
with tracer.start_as_current_span("pr_review") as span:
    span.set_attributes({
        "user.id": user_id,
        "team.id": team_id,
        "model.alias": "sonnet",
        "model.id": "claude-sonnet-4-6",
        "provider": "anthropic",
        "tier": 1,
        "data.classification": "INTERNAL",
        "cost.usd": 0.045,
        "latency.ms": 3420,
        "pii.detected": False,
        "cache.hit": True,
    })
```

### Cost Attribution Queries (TimescaleDB)

```sql
-- Cost per team this month
SELECT team_id,
       SUM(cost_usd) AS total_cost,
       COUNT(*) AS call_count,
       AVG(cost_usd) AS avg_cost_per_call
FROM inference_audit_log
WHERE timestamp >= date_trunc('month', NOW())
GROUP BY team_id
ORDER BY total_cost DESC;

-- Provider tier distribution (cost optimization signal)
SELECT tier,
       provider,
       model_alias,
       COUNT(*) AS calls,
       SUM(cost_usd) AS cost
FROM inference_audit_log
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY tier, provider, model_alias;

-- RESTRICTED data verification (compliance report)
SELECT COUNT(*) AS restricted_cloud_violations
FROM inference_audit_log
WHERE data_class = 'RESTRICTED' AND tier = 1;
-- This must always return 0. Alert if non-zero.
```

### Required Prometheus Metrics

```yaml
gateway_requests_total{team_id, model_alias, provider, tier, status}
gateway_latency_seconds{endpoint, percentile}
inference_cost_usd_total{team_id, model_alias, provider, tier}
pii_detections_total{severity, entity_type}
budget_utilization_ratio{team_id}          # Alert at 0.7 and 0.9
circuit_breaker_state{provider}            # 0=closed, 1=half-open, 2=open
provider_health_up{provider, tier}         # 0=down, 1=up
embedding_request_duration_ms{provider}
restricted_data_cloud_violations_total     # Must always be 0; alert on any increment
```

---

## 7. Evaluation Pipeline

### Golden Dataset

```python
# evals/golden_dataset.py
GOLDEN_CASES = [
    {
        "id": "security-sql-001",
        "diff": "...",  # SQL injection vulnerability
        "expected_flags": ["sql_injection"],
        "expected_severity": "critical",
    },
    {
        "id": "security-auth-001",
        "diff": "...",  # Missing authentication
        "expected_flags": ["missing_auth"],
        "expected_severity": "high",
    },
    # 100 cases covering security, performance, style, and false-positive scenarios
]

def evaluate_model(model_alias: str, test_cases: list) -> dict:
    """
    Runs evaluation suite. New model alias must beat current baseline by ≥5% F1.
    Uses Batch API for 50% cost savings on eval runs.
    """
    results = []
    for case in test_cases:
        review = CodeReviewer(model_alias=model_alias).review(diff=case["diff"])
        results.append({
            "precision": calculate_precision(review, case),
            "recall": calculate_recall(review, case),
        })
    f1 = harmonic_mean([r["precision"] for r in results], [r["recall"] for r in results])
    return {"f1": f1, "results": results}
```

### Model Upgrade Process

```
1. New Anthropic model released (e.g., claude-sonnet-4-7)
2. Platform team adds candidate ID to model_registry.yaml under a new alias "sonnet-next"
3. Run eval suite: python evals/run_regression.py --model sonnet-next
4. If F1(sonnet-next) >= F1(sonnet) * 1.05:
   - Update "sonnet" alias in registry to point to new model ID
   - A/B test: Route 10% of traffic to new alias for 48 hours
   - Monitor: Error rate, latency, developer feedback
   - If stable: Route 100%
5. If eval fails: Block upgrade; notify team; do not update registry
```

---

## 8. Disaster Recovery

### Failover Chain

```
PRIMARY:   Anthropic (claude-sonnet-4-6, claude-opus-4-7)
           ↓ [circuit breaker: 3 failures in 60s]
SECONDARY: Azure OpenAI Canada (claude-sonnet-4-6 via AI Foundry)
           ↓ [circuit breaker: 3 failures in 60s]
TERTIARY:  vLLM on-prem (llama3.3:70b-instruct-q4_K_M)
           ↓ [if vLLM GPU server down]
OFFLINE:   Ollama (qwen2.5-coder:32b or llama3.2:8b depending on VRAM available)
```

**PIPEDA note**: This chain is correct. The old chain (Anthropic → US OpenAI → Llama) was not PIPEDA-safe because US OpenAI is a US-based company. Azure AI Foundry via Canada region is PIPEDA-compliant.

### DR Targets

| Metric | Target | Measurement |
|---|---|---|
| RTO (Recovery Time Objective) | 30 minutes | Time from incident detection to restored service |
| RPO (Recovery Point Objective) | 1 hour | Maximum data loss in audit logs |
| Anthropic outage failover | <2 minutes | Automatic, no manual intervention |
| Audit log retention | 7 years | S3 Object Lock (write-once) |

### Quarterly DR Drill

```bash
# Simulate Anthropic outage
kubectl exec -n ai-gateway deployment/circuit-breaker -- \
  force-open --provider=anthropic --duration=30m

# Verify: All traffic routes to Azure Canada
./scripts/verify_failover.sh --expect-provider=azure_openai

# Verify: RESTRICTED data still routes to vLLM (not Azure)
./scripts/verify_restricted_routing.sh --expect-tier=2

# Restore
kubectl exec -n ai-gateway deployment/circuit-breaker -- \
  close --provider=anthropic
```

---

## 9. Scalability

### Horizontal Scaling Targets

| Component | Min Pods | Max Pods | Scale Trigger |
|---|---|---|---|
| API Gateway | 3 | 50 | CPU >70% |
| Sidekiq Workers | 5 | 200 | Queue depth >100 jobs |
| PII Scanner (Presidio) | 2 | 20 | CPU >60% |
| LLM Guard | 2 | 10 | CPU >60% |

### Load Scenarios

```
Current (Year 1):
- 500 developers, 20 calls/day each
- Peak: 10,000 calls/day (~7/minute)
- Cost at target routing: ~$3,750/month

Growth (Year 2, 1,500 developers, 50 calls/day):
- 75,000 calls/day (~52/minute)
- Cost at target routing: ~$14,000/month

Peak Load (all-hands deploy event):
- 200 calls/minute for 4 hours
- Requires: 50 gateway pods, 200 Sidekiq workers
```

---

## 10. Security Architecture

### Threat Model (STRIDE)

| Threat | Attack | Control |
|---|---|---|
| **Spoofing** | Fake GitHub webhook | HMAC-SHA256 signature verification + IP allowlist |
| **Tampering** | Modify prompt in transit | mTLS service-to-service; request signing |
| **Repudiation** | Deny making a request | Immutable audit log (S3 Object Lock); trace ID in every call |
| **Info Disclosure** | PII in response | Output validation: scan response for secrets/PII before delivery |
| **DoS** | Budget exhaustion attack | Pre-flight budget check; per-team rate limits; anomaly detection |
| **Elevation** | Prompt injection to bypass RBAC | LLM Guard classifier; role validation independent of LLM output |

### Webhook Security

```python
class GitHubWebhookValidator:
    def validate(self, payload: bytes, signature: str, delivery_id: str) -> bool:
        # 1. Verify HMAC-SHA256 signature
        expected = "sha256=" + hmac.new(
            self.secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise WebhookSignatureInvalid("Signature mismatch")

        # 2. Replay attack prevention
        if self.redis.exists(f"webhook:delivery:{delivery_id}"):
            raise ReplayAttackDetected(f"Delivery {delivery_id} already processed")
        self.redis.setex(f"webhook:delivery:{delivery_id}", 86400, "1")

        # 3. IP allowlist (GitHub publishes IP ranges via API)
        client_ip = self.request.remote_ip
        if not self.ip_in_github_ranges(client_ip):
            raise WebhookIPNotAllowed(f"IP {client_ip} not in GitHub IP ranges")

        return True
```

---

## 11. API Versioning

```
/api/v1/inference   — Current stable
/api/v2/inference   — Future (breaking changes announced 6 months ahead)

Deprecation headers:
  Deprecation: Sat, 01 Jan 2028 00:00:00 GMT
  Sunset: Fri, 01 Jul 2028 00:00:00 GMT
  Link: <https://docs.company.com/migrate-v1-v2>; rel="deprecation"

Support policy:
  - v1 supported for 12 months after v2 launch
  - Migration guide + CLI tooling provided
  - Office hours: Platform team available for migration pairing
```

---

## Architecture Decision Records

**ADR-001: Three-Tier Provider Model**
Tier 1 (Cloud): Anthropic + Azure OpenAI Canada; Tier 2 (On-prem): vLLM; Tier 3 (Offline): Ollama.
Rationale: PIPEDA compliance, resilience, offline capability. Azure Canada (not US OpenAI) as secondary ensures PIPEDA-safe cloud fallback.

**ADR-002: Canonical Model Registry**
Single YAML maps aliases to provider strings. Model IDs never appear in application code.
Rationale: Anthropic has changed naming conventions multiple times. One config file update vs. N code changes.

**ADR-003: ABC Interfaces for Providers**
`LLMProvider` and `EmbeddingProvider` ABCs. All provider access through `ProviderFactory` and `EmbeddingProviderFactory`.
Rationale: Testability; provider swaps without code changes; PIPEDA compliance as code invariant.

**ADR-004: Decomposed Governance Layer**
LiteLLM (routing) + Presidio (PII) + LLM Guard (injection) + Kong/Tyk (orchestration).
Rationale: LiteLLM does not natively handle PII or injection defense. Separate services for single responsibility and independent scaling.

**ADR-005: Async-First Architecture**
All LLM calls via Sidekiq (Ruby) / Celery (Python). Webhook returns HTTP 202 immediately.
Rationale: GitHub webhooks timeout at 10s. Claude Sonnet PR review takes 30-60s.

**ADR-006: Rules-Based Compliance Routing**
Classification-then-routing: `classify()` runs before `route()`.
Rationale: PIPEDA compliance cannot rely on probabilistic ML routing. Rules are auditable and testable.

**ADR-007: Opus 4.7 Tokenizer Safety Margin**
1.35x multiplier on Opus alias cost estimates in `AnthropicProvider.estimate_cost_usd()`.
Rationale: New tokenizer generates up to 35% more tokens for same input. Without margin, budget checks underestimate cost.

**ADR-008: 768-dim Canonical Embedding Dimension**
All indexes use 768-dim (BGE-M3 on vLLM, nomic-embed-text on Ollama). OpenAI 1536-dim only for PUBLIC data in separate index.
Rationale: Cannot mix dimensions in same index. RESTRICTED data must use on-prem 768-dim provider. Consistency beats OpenAI's slightly higher representational capacity.
