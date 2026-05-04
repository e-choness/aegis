# Enterprise AI Platform — Consolidated Project Overview
# Version 2.0 — Updated May 2026

> **What changed in v2**: All model names updated to current active models. Pricing corrected (Haiku 4.5: $1/$5; Sonnet 4.6: $3/$15; Opus 4.7: $5/$25). Cross-document conflicts on fallback chain resolved. Provider-agnostic interface design formalized. Ollama offline tier fully specified. Technical tradeoffs added for key architectural decisions.

---

## Executive Summary

### Mission & Value Proposition
Build a **production-grade AI governance platform** that consolidates fragmented AI tooling into a centralized, secure infrastructure for 500+ engineers across a polyglot technology stack. This platform transforms developer productivity while maintaining the strict regulatory compliance requirements of a financial services organization operating under Canadian PIPEDA.

**Core Value Drivers:**
- **Productivity**: 40-60% reduction in code review cycle time, saving $2-4M annually in engineering capacity
- **Cost Optimization**: 60-80% reduction in AI inference costs through intelligent model routing and prompt caching
- **Risk Mitigation**: Prevents data leakage incidents averaging $4.45M per breach in financial services
- **Compliance**: Complete audit trail meeting SOC 2, PIPEDA, and PCI-DSS requirements
- **Resilience**: Three-tier provider fallback including offline-capable Ollama tier

**ROI**: 24x return on investment ($3.9M value created vs. $161K annual operating cost)

---

## Scope Summary

### In Scope
1. **AI Gateway Foundation**: Centralized governance chokepoint with authentication, data classification, PII masking, prompt injection defense, and cost attribution
2. **PR Review Automation**: AI-assisted code reviews with automated approval for low-risk changes
3. **Polyglot SDK Ecosystem**: Native libraries for Ruby, Python, TypeScript, Kotlin with standardized retry/auth logic and provider-agnostic interfaces
4. **RAG System**: Vector database indexing internal documentation via provider-agnostic `EmbeddingProvider` interface
5. **Observability Platform**: Distributed tracing, cost dashboards, quality evaluation pipeline
6. **Developer Tooling**: IDE extensions (VS Code, JetBrains), Slack bot, CLI tools

### Out of Scope (Explicitly)
- Customer-facing AI features (separate product workstream)
- Model training/fine-tuning infrastructure (future phase)
- CI/CD pipeline replacement (integration only)

---

## Key Stakeholders

### Primary Users
- **Engineering Teams** (500+ developers): Consume AI services via SDKs, IDE extensions, PR reviews
- **Platform Engineering**: Own infrastructure, maintain gateway, manage costs
- **Security & Compliance**: Define policies, audit trails, approve data handling
- **Finance**: Budget allocation, cost attribution, chargeback to teams

### Decision Makers
- **VP Engineering**: Budget approval, strategic alignment, resource allocation
- **CISO**: Security controls, compliance sign-off, incident response
- **CFO**: Financial justification, ROI validation, operating budget

### External Dependencies
- **Anthropic**: Primary LLM provider (Data Processing Agreement required before launch)
- **Azure (Canada region)**: Secondary LLM provider via Azure AI Foundry (PIPEDA-compliant)
- **GitHub**: Source of PR webhooks, target for review comments
- **Okta/Azure AD**: SSO authentication provider
- **HashiCorp / AWS**: Secrets management (Vault or Secrets Manager)

---

## Success Metrics

### Operational Targets (6 Months)
| Metric | Target | Measurement |
|--------|--------|-------------|
| **Adoption Rate** | 80% of teams using ≥1 feature | SDK downloads, API calls per team |
| **Availability** | 99.9% uptime | Gateway health checks, incident logs |
| **Latency** | p95 < 5s for PR reviews | OpenTelemetry traces |
| **Cost per Developer** | <$322/year | Total spend ÷ active users |
| **Security** | Zero PII leakage incidents | PII scanner logs, security audits |
| **Data Residency** | Zero RESTRICTED data to cloud | Audit log provider field |

### Business Outcomes (12 Months)
- **Productivity**: 25% reduction in PR-to-merge cycle time
- **Quality**: 15% reduction in production incidents from code review gaps
- **Cost Efficiency**: AI spend per developer decreases 40% while usage increases 3x
- **Innovation**: 5+ new AI-enabled features shipped that weren't feasible pre-platform
- **Compliance**: Pass audit with zero findings on AI governance controls

### Leading Indicators (Track Monthly)
- Developer satisfaction (NPS) above 40
- Time from "request access" to "first successful API call" under 1 hour
- SDK download rate trending upward
- Cost per inference call trending downward
- Percentage of calls served by Tier 2/3 (cost efficiency signal)

---

## Top Risks & Mitigation Strategies

### 1. Cloud Provider API Reliability (CRITICAL)
**Risk**: Cloud LLM providers target 99.5% uptime; outages block all PR reviews.

**Mitigation**:
- **Three-tier fallback**: Anthropic (primary) → Azure OpenAI Canada (secondary) → vLLM on-prem → Ollama offline
- **Circuit breaker**: Auto-switch after 3 consecutive failures within 60s
- **Async queue**: Requests queue during outages; processed when provider recovers
- **Health check**: Ping each provider every 30s; PagerDuty alert on failover

**Tradeoff**: More tiers = more resilience but more operational complexity. The Ollama tier adds ~$15K in GPU hardware but eliminates any single-provider dependency.

---

### 2. PIPEDA/GDPR Data Residency Violations (BLOCKER)
**Risk**: Sending Canadian customer data to US-based Anthropic violates PIPEDA; C$100K+ fine per incident.

**Mitigation**:
- **Data classification layer**: Tag every prompt as RESTRICTED/CONFIDENTIAL/INTERNAL/PUBLIC before routing
- **Hard routing rule (enforced in code)**: RESTRICTED → only vLLM (Tier 2) or Ollama (Tier 3) — never Tier 1
- **PII masking**: Microsoft Presidio scans prompts before any external API call
- **PIPEDA-safe secondary**: Azure OpenAI via Canada region (not US OpenAI) for cloud fallback
- **DPA required**: Data Processing Agreement with Anthropic signed before any data flows

**Tradeoff**: Hard routing rule in code vs. policy document. Code wins — a policy document can be overlooked; a routing invariant cannot.

---

### 3. Runaway Costs from Misconfiguration (CRITICAL)
**Risk**: One team accidentally calls Opus in a loop, burning $50K over a weekend.

**Mitigation**:
- **Hard budget caps**: Per-team monthly limits enforced at gateway (HTTP 429 when exceeded)
- **Pre-flight cost estimation**: Gateway estimates cost before calling provider; rejects if budget insufficient
- **Opus 4.7 safety margin**: Cost estimates apply 1.35x multiplier (new tokenizer can generate up to 35% more tokens)
- **Anomaly detection**: Alert if team exceeds 3x their 30-day average spend
- **Emergency kill switch**: Disable specific teams/models within 5 minutes

---

### 4. Low Developer Adoption (ORGANIZATIONAL)
**Risk**: Engineers don't trust AI reviews; adoption stagnates at 15%.

**Mitigation**:
- **Pilot program**: 3 teams (10 engineers) in Month 2; collect structured feedback
- **Champion program**: 1 advocate per team for peer support and evangelism
- **SDK friction reduction**: Same 3-line API call in Ruby, Python, TypeScript, Kotlin
- **Offline mode**: Ollama tier ensures AI features work without cloud — builds trust in reliability

---

### 5. Model Quality Degradation Undetected (CRITICAL)
**Risk**: Anthropic releases a new model; platform auto-upgrades; PR review quality drops; nobody notices for weeks.

**Mitigation**:
- **Model alias registry**: New model IDs are added to `model_registry.yaml`; no automatic upgrades
- **Golden dataset**: 100 human-labeled PRs covering security, performance, style
- **Quality gates**: New model must beat baseline by ≥5% F1 before alias is updated
- **A/B testing**: Route 10% of traffic to new model version before full rollout
- **Auto-rollback**: If error rate spikes >10% in 1 hour, revert alias in config

---

## Resolved Architectural Conflicts (from Cross-Document Audit)

### Conflict 1: Fallback Chain Inconsistency — RESOLVED
**Problem**: Documents contradicted on secondary provider (OpenAI vs Azure OpenAI vs nothing).
**Resolution**: Canonical three-tier chain:
- Tier 1A: Anthropic (primary)
- Tier 1B: Azure OpenAI via **Canada region** (secondary — PIPEDA-compliant; not US OpenAI)
- Tier 2: vLLM on-prem (RESTRICTED data; cost fallback)
- Tier 3: Ollama (offline; always available)

### Conflict 2: PIPEDA Violation in DR Plan — RESOLVED
**Problem**: Disaster recovery plan said to failover RESTRICTED data to US-based OpenAI.
**Resolution**: Data classifier runs before the router. RESTRICTED data routing to cloud is a code invariant enforced in `ModelRouter.route()` — it cannot be overridden by an operational runbook.

### Conflict 3: Provider Hardcoding in RAG Pipeline — RESOLVED
**Problem**: `OpenAIEmbedding` was hardcoded in the RAG pipeline (LlamaIndex import).
**Resolution**: All embedding access goes through `EmbeddingProviderFactory`, which routes by data classification and health — same pattern as completion routing.

### Conflict 4: Model Naming Inconsistency — RESOLVED
**Problem**: Three naming schemes (`claude-haiku-3`, `claude-3-haiku`, `claude-3-haiku-20240307`) across documents.
**Resolution**: All model IDs live in `model_registry.yaml`. Application code uses only canonical aliases (`haiku`, `sonnet`, `opus`, `local`). Retired IDs removed entirely.

### Conflict 5: LiteLLM Governance Scope — RESOLVED
**Problem**: Specs implied LiteLLM handles PII masking and prompt injection natively (it does not).
**Resolution**: Governance layer is decomposed into distinct services:
- LiteLLM → model routing and load balancing only
- Presidio → PII detection and masking
- LLM Guard → prompt injection defense
- Kong/Tyk → API gateway orchestrating all three

### Critical Gap: Ollama Offline Tier — RESOLVED
**Problem**: Ollama was mentioned as a footnote with zero specification.
**Resolution**: Ollama is a fully specified Tier 3 provider with its own `OllamaProvider` and `OllamaEmbeddingProvider` implementations, health check, model registry entries, and acceptance criteria (FR-5: Offline Mode).

---

## Current Model Pricing (May 2026)

> **Note on Opus 4.7**: The per-token rate is unchanged from Opus 4.6 ($5/$25), but Anthropic's new tokenizer generates up to 35% more tokens for the same input text. Budget pre-flight checks use a 1.35x safety multiplier for Opus alias calls.

| Alias | Provider Model | Input $/MTok | Output $/MTok | Context |
|---|---|---|---|---|
| `haiku` | `claude-haiku-4-5-20251001` | $1.00 | $5.00 | 200K |
| `sonnet` | `claude-sonnet-4-6` | $3.00 | $15.00 | 1M |
| `opus` | `claude-opus-4-7` | $5.00 | $25.00 | 1M |
| vLLM (Tier 2) | Llama 3.3 70B / Devstral 24B | ~$0.10 (amortized) | ~$0.10 | 8K-32K |
| Ollama (Tier 3) | qwen2.5, nomic-embed-text | $0.00 | $0.00 | 8K-128K |

Batch API discount: 50% off for async workloads (evals, nightly processing).
Prompt caching: Up to 90% savings on repeated system prompts.

---

## Resource Requirements & Timeline

### Team Structure
- **Platform Engineers** (2 FTEs): Gateway, orchestration, SDK architecture
- **Backend Engineers** (2 FTEs): Job queues, APIs, database schema
- **ML Engineer** (1 FTE): RAG pipeline, eval framework, prompt optimization
- **Security Specialist** (1 FTE): PII masking, threat modeling, compliance audits
- **Total**: 6 FTEs for 12 months

### Budget
- **Infrastructure**: $15-25K/month (LLM APIs, observability, cloud hosting, GPU for vLLM)
- **Salaries**: $1.2M (6 FTEs × $200K loaded cost)
- **Total Year 1**: ~$1.5M investment
- **Break-even**: Month 14 (based on $4.7M productivity gains)

### Phased Rollout
- **Phase 1 (Months 1-3)**: Core gateway, AuthN/AuthZ, single model (sonnet alias), Ruby SDK, Anthropic provider
- **Phase 2 (Months 4-6)**: PII masking, async queue (Sidekiq/Celery), observability, polyglot SDKs, Azure Canada fallback
- **Phase 3 (Months 7-9)**: vLLM Tier 2 deployment, RAG system with `EmbeddingProviderFactory`, eval pipeline
- **Phase 4 (Months 10-12)**: Ollama Tier 3, multi-region, chaos engineering, GA launch
- **Pilot** (Month 2): AI Platform team (5 engineers)
- **Beta** (Month 6): 50 engineers
- **GA** (Month 12): 500+ engineers

---

## Approval Blockers & Next Steps

### Must-Have Before Production Launch
1. **Authentication/AuthZ Spec** (Owner: Security Architect, ETA: Week 3) — SSO (Okta), RBAC (OPA), JWT
2. **Data Classification Policy** (Owner: Legal + Compliance, ETA: Week 4) — RESTRICTED/CONFIDENTIAL/INTERNAL definitions, routing rules, DPA with Anthropic
3. **Disaster Recovery Plan** (Owner: Platform SRE, ETA: Week 5) — Failover testing, RTO: 30min, RPO: 1hr
4. **Model Registry Ratified** (Owner: Platform Arch, ETA: Week 2) — YAML approved by Security and Engineering

### Conditional Approval Gates
- [ ] Security review: threat model, penetration test results
- [ ] Legal sign-off: PIPEDA compliance approach and DPA with Anthropic
- [ ] Finance approval: $1.5M Year 1 budget
- [ ] ARB re-approval after all blocker gaps addressed
- [ ] Retired model IDs purged from all configuration files

---

## Why This Matters (Strategic Context)

This is **not a developer productivity hack** — it's the **control plane for enterprise AI adoption**. Without this platform:
- Every team builds custom LLM integrations → fragmented security, no cost control
- No audit trail → cannot pass SOC 2 audits or respond to regulatory inquiries
- Direct API access → developers bypass PII scanning, PIPEDA violations waiting to happen
- No quality measurement → cannot tell if AI is helping or hurting code quality
- No offline tier → AI features fail when network is unavailable

With this platform:
- **100% of AI calls governed**: Single gateway enforces policy, blocks PII, tracks costs
- **Audit-ready**: Every request logged with user, team, model alias, provider, tier, cost, timestamp
- **Cost-optimized**: Prompt caching (up to 90% savings) + smart routing saves $120K-180K/year
- **Compliant**: PIPEDA/GDPR controls are code invariants, not policy documents
- **Measurable**: Evals pipeline proves AI improves productivity objectively
- **Resilient**: Ollama tier means AI features work on a plane with no Wi-Fi

**Bottom Line**: This platform is the foundation every future AI initiative will build on. Get it right once, unlock 5 years of innovation.
