# Architecture Review Board: Critical Analysis
# Enterprise AI Platform for Developer Productivity
# Version 2.0 — Updated May 2026

> **What changed in v2**: All blocker and critical findings from v1 have been addressed and documented. Model IDs updated to active versions. Pricing corrected. Fallback chain conflict resolved. Provider-agnostic interfaces specified. Ollama tier fully described. Technical tradeoffs added to each decision. Status updated to reflect remediation.

---

## EXECUTIVE SUMMARY

**RECOMMENDATION: CONDITIONAL APPROVAL** — Architecture has been significantly hardened. Original 8 blockers and 12 critical omissions from v1 are remediated in v2. Remaining conditions are process and legal gates, not architectural gaps.

**Overall Assessment**: The conceptual four-layer separation is sound and the operational detail now meets enterprise-grade standards. The provider-agnostic interface design is the most significant improvement from v1 — it enforces PIPEDA compliance as a code invariant rather than a policy document.

---

## STATUS OF ORIGINAL FINDINGS

### Blockers — All Addressed

| Blocker | v1 Status | v2 Status | Resolution |
|---|---|---|---|
| No Identity & Access Management | ❌ Missing | ✅ Resolved | SSO (Okta/Azure AD) + OPA RBAC + mTLS service mesh specified |
| No Data Classification | ❌ Missing | ✅ Resolved | RESTRICTED/CONFIDENTIAL/INTERNAL/PUBLIC with routing rules in code |
| No Horizontal Scaling | ❌ Missing | ✅ Resolved | Kubernetes HPA specified for gateway (3-50 pods), worker pool (5-200) |
| No Disaster Recovery | ❌ Missing | ✅ Resolved | RTO: 30min, RPO: 1hr; four-tier fallback chain; quarterly DR drills |
| No Cost Model | ❌ Missing | ✅ Resolved | Full cost model at current pricing; $82/developer/year at target routing |
| No Org Change Management | ❌ Missing | ✅ Resolved | Pilot (Month 2), champion program, all-hands demo, incentive structure |
| No Testing Strategy | ❌ Missing | ✅ Resolved | Unit/integration/load/chaos engineering plan specified |
| No GDPR/PIPEDA Compliance | ❌ Missing | ✅ Resolved | DPA required; data classification hard-coded routing; 7yr audit log |

### Critical Findings — All Addressed

| Critical Finding | v1 Status | v2 Status | Resolution |
|---|---|---|---|
| No Async Job Queue | ❌ Missing | ✅ Resolved | Sidekiq (Ruby) + Celery (Python); GitHub webhook returns 202 immediately |
| No Observability | ❌ Missing | ✅ Resolved | OpenTelemetry + Prometheus + Grafana + PagerDuty specified |
| No Evals Pipeline | ❌ Missing | ✅ Resolved | Golden dataset, A/B testing, quality gates, auto-rollback |
| No Polyglot SDK spec | ❌ Missing | ✅ Resolved | Ruby gem, Python pkg, TypeScript npm, Kotlin maven; error normalization |
| No Secrets Management | ❌ Missing | ✅ Resolved | HashiCorp Vault; 90/30/7-day rotation; runtime injection |
| Smart Router too vague | ❌ Vague | ✅ Resolved | Decision matrix: task type + complexity + data classification + budget |
| Quota Management | ❌ Missing | ✅ Resolved | Per-team hard limits; 70%/90%/100% alerts; pre-flight estimation |
| GitHub Webhook Security | ❌ Missing | ✅ Resolved | HMAC-SHA256 verification; replay prevention; IP allowlisting |
| API Versioning | ❌ Missing | ✅ Resolved | /api/v1/ from day 1; 12-month deprecation window; migration tooling |
| Incident Response | ❌ Missing | ✅ Resolved | Key rotation runbook; 15-minute containment target; PIR process |
| Financial Audit Trail | ❌ Missing | ✅ Resolved | 7-year retention; S3 Object Lock; cryptographic hash chain |
| IDE Extension Distribution | ❌ Missing | ✅ Resolved | Internal registry (Artifactory); auto-update; JetBrains support |

---

## REMAINING CONDITIONS FOR APPROVAL

The following items require completion before production launch but are not architectural blockers — they are legal, organizational, and process gates.

### Condition 1: Data Processing Agreement with Anthropic
**Status**: Required before any customer-adjacent data flows to Anthropic.
**Owner**: Legal + VP Engineering
**ETA**: Week 4
**What's needed**: Signed DPA guaranteeing customer data is not used for model training; 30-day deletion from Anthropic logs; Canadian data sovereignty provisions where possible.

### Condition 2: Formal Data Classification Policy Document
**Status**: Code enforces the classification rules; policy document needed for audit.
**Owner**: Legal + Compliance + CISO
**ETA**: Week 4
**What's needed**: Formal definition of RESTRICTED/CONFIDENTIAL/INTERNAL/PUBLIC; examples for engineers; sign-off from CISO.

### Condition 3: Penetration Testing of Gateway
**Status**: Architecture specifies defenses; they need external validation.
**Owner**: Security Team + External Vendor
**ETA**: Month 3
**What's needed**: Prompt injection, webhook spoofing, PII bypass, and budget exhaustion attack scenarios tested by external red team.

### Condition 4: GPU Hardware Procurement for Tier 2
**Status**: vLLM on-prem required for RESTRICTED data; hardware not yet ordered.
**Owner**: Platform Engineering + Finance
**ETA**: Month 2
**What's needed**: Minimum 2× NVIDIA A100 80GB (or equivalent) to serve Llama 3.3 70B at Q4_K_M quantization (~43GB VRAM required); redundant setup for 99.9% uptime.

---

## TECHNICAL TRADEOFFS — BOARD REVIEW

### Tradeoff 1: Rules-Based Routing vs. ML-Based Routing

**Decision**: Rules-based (implemented)

| Dimension | Rules-Based | ML-Based |
|---|---|---|
| Auditability | ✅ Every decision traceable in code | ❌ Black box |
| Compliance risk | ✅ Cannot accidentally route RESTRICTED to cloud | ❌ Model miscalibration = PIPEDA violation |
| Maintenance | ❌ Manual threshold tuning as model capabilities evolve | ✅ Auto-adapts to new models |
| Test coverage | ✅ Unit-testable, deterministic | ❌ Requires statistical validation |

**Board Note**: ML-based routing for cost optimization (not compliance decisions) is appropriate for a future phase once the rules-based system is established. Compliance routing must always remain rules-based.

---

### Tradeoff 2: Three-Tier Provider Architecture vs. Two-Tier

**Decision**: Three-tier (Anthropic → Azure Canada → vLLM → Ollama)

| Dimension | Three-Tier | Two-Tier (Cloud + On-prem) |
|---|---|---|
| PIPEDA compliance | ✅ RESTRICTED stays on-prem regardless of cloud health | Same |
| Offline capability | ✅ Tier 3 works with no network | ❌ Requires at least on-prem network |
| Operational complexity | ❌ Three systems to maintain | ✅ Simpler |
| Cost | ❌ GPU server ($30-50K) + Ollama setup overhead | ✅ No Ollama hardware |
| Developer experience | ✅ AI features work on flights, air-gapped CI | ❌ Fails without network |

**Board Note**: The Ollama tier is the difference between "AI that usually works" and "AI that always works." For a fintech, reliability is a compliance argument — AI-assisted security reviews that fail when the developer is on a VPN with network issues are not useful.

---

### Tradeoff 3: ABC Interface vs. Protocol for Provider Abstraction

**Decision**: ABC (Abstract Base Class)

| Dimension | ABC | Protocol (structural subtyping) |
|---|---|---|
| Enforcement | ✅ Missing method detected at class definition | ❌ Detected at call site |
| Flexibility | ❌ Requires inheritance | ✅ Any class with matching signature works |
| Error messages | ✅ Clear "must implement X" | ❌ Confusing type errors at runtime |
| Use case fit | ✅ All providers are internal code | Protocol better for third-party libraries |

---

### Tradeoff 4: LiteLLM as Monolith vs. Decomposed Governance

**v1 Problem**: Specifications implied LiteLLM handles PII masking and prompt injection natively. It does not.

**Decision**: Decomposed services

| Component | Responsibility |
|---|---|
| LiteLLM | Model routing, load balancing, provider abstraction |
| Microsoft Presidio | PII detection and masking (open-source NER) |
| LLM Guard | Prompt injection detection |
| Kong/Tyk | API gateway orchestrating all three |

**Tradeoff**:
- Pro: Each service has one responsibility; independently testable, scalable, replaceable
- Con: More services to operate; inter-service latency adds ~5-15ms
- Decision: Independence wins; the combined latency is still under the 20ms gateway overhead target

---

### Tradeoff 5: Embedding Vector Dimensions (768 vs. 1536)

**Decision**: 768-dim as canonical dimension

**Problem Addressed**: `OpenAIEmbedding` (1536-dim) was hardcoded in the RAG pipeline. Cannot mix dimensions in the same vector DB index. RESTRICTED data cannot use OpenAI embeddings (PIPEDA).

**Resolution**:
- **Single canonical index**: 768-dim (BGE-M3 on vLLM, nomic-embed-text on Ollama)
- **Separate index for PUBLIC data**: 1536-dim (OpenAI text-embedding-3-small) if team chooses
- All routing through `EmbeddingProviderFactory` — same three-tier logic as completion routing

| Provider | Model | Dimensions | Max Tokens | Data Classes | Notes |
|---|---|---|---|---|---|
| OpenAI (Tier 1) | text-embedding-3-small | 1536 | 8191 | PUBLIC, INTERNAL | Not for RESTRICTED/CONFIDENTIAL |
| vLLM (Tier 2) | bge-m3 | 768 | 8192 | All | Multilingual; production-grade |
| Ollama (Tier 3) | nomic-embed-text | 768 | 8192 | All | 274MB; beats ada-002 on retrieval |

---

### Tradeoff 6: Opus 4.7 Tokenizer Inflation

**Finding**: Anthropic's Claude Opus 4.7 (released April 2026) uses a new tokenizer that generates up to 35% more tokens for the same input text compared to Opus 4.6. The per-token price is unchanged ($5/$25 per MTok) but effective cost per request increases.

**Impact**: A budget pre-flight check that approved a request under Opus 4.6 pricing may allow a request that exceeds budget under Opus 4.7.

**Resolution**:
- Model registry documents `tokenizer_inflation_factor: 1.35` for `opus` alias
- `AnthropicProvider.estimate_cost_usd()` applies 1.35x safety multiplier for Opus calls
- Unit test verifies the multiplier is applied
- **Recommendation**: Benchmark actual Opus 4.7 token usage on your workloads. The 35% is a ceiling; typical workloads may see 10-20% increase.

---

## OUTSTANDING RISKS (Downgraded from Blocker)

### Risk 1: Open-Source Tool Lifecycle
**Status**: MAJOR (not blocker)
**Concern**: LiteLLM (~3 core maintainers), Presidio (Microsoft-backed, lower risk), LLM Guard (small team).
**Mitigation in v2**:
- Open-source adoption policy: >5 contributors, active commits, permissive license required
- Internal fork of critical dependencies on GitHub Enterprise
- Documented escape hatches: "If LiteLLM abandoned, replace with Kong + custom Lua plugin"
- 1 engineer designated as codebase expert per OSS dependency

### Risk 2: RAG Document Freshness
**Status**: MAJOR (not blocker)
**Concern**: Architecture docs change; RAG returns stale answers.
**Mitigation in v2**:
- Index refresh: Every 6 hours via scheduled job
- Staleness alert: Flag docs not updated in 90 days
- Source ranking: Production docs > wikis > Slack exports
- Metadata filtering: RAG returns last_updated timestamp with every result

### Risk 3: vLLM Quality Gap
**Status**: MAJOR (not blocker)
**Concern**: On-prem Llama 3.3 70B is lower quality than Anthropic Opus 4.7 for complex reasoning.
**Mitigation**:
- Task-type segregation: Complex security audits do not use RESTRICTED-classified repos where possible
- Prompt engineering: Compensate for capability gap with more structured prompts on Tier 2
- Quality evals: Separate golden datasets for Tier 1 and Tier 2 models; track separately

---

## ARCHITECTURE APPROVAL DECISION

### Board Vote

| Board Member | Vote | Condition |
|---|---|---|
| Chief Architect | ✅ Approve | DPA with Anthropic signed before launch |
| CISO | ✅ Approve | Pen test completed by Month 3 |
| VP Engineering | ✅ Approve | GPU hardware procured |
| Legal | ⏳ Pending | Data classification policy finalized |
| Security Architect | ✅ Approve | No additional conditions |
| ML Engineering Lead | ✅ Approve | Evals pipeline in scope for Phase 3 |
| Finance | ✅ Approve | GPU hardware approved in capital budget |

**Current Status**: 6 approve / 0 reject / 1 pending (Legal)

**Approval Path**: Legal sign-off expected Week 4. Architecture can proceed to implementation immediately for Phases 1 and 2. Phase 3 (vLLM + RAG with RESTRICTED data) gates on Legal sign-off and GPU hardware arrival.

---

## CRITICAL PATH TO PRODUCTION

| Week | Owner | Deliverable |
|---|---|---|
| 1-2 | Security Arch | AuthN/AuthZ spec: SSO integration, OPA policy engine, mTLS |
| 2 | Platform Arch | Model registry YAML ratified; retired IDs confirmed removed |
| 3-4 | Legal + Eng | Data Processing Agreement with Anthropic; classification policy |
| 4-8 | Platform Eng | Gateway MVP: auth, Anthropic provider, Ruby SDK, async queue |
| 5-6 | Finance + Eng | GPU server hardware ordered and delivered |
| 8 | Security | External penetration test of gateway |
| 9-12 | Platform Eng | Phase 2: PII masking, observability, polyglot SDKs, Azure Canada |
| 13-16 | Platform Eng | Phase 3: vLLM Tier 2, RAG, evals pipeline |
| 17-20 | Platform Eng | Phase 4: Ollama Tier 3, chaos engineering, GA launch |

**Minimum Time to Production-Ready (Phase 1-2)**: 12 weeks
**Full Enterprise-Grade Maturity**: 20 weeks
