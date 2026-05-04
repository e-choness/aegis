# Executive Summary: Enterprise AI Platform Architecture
# Version 2.0 — Updated May 2026

> **What changed in v2**: Model pricing updated to current rates (Haiku 4.5: $1/$5; Sonnet 4.6: $3/$15; Opus 4.7: $5/$25 — a 67% reduction from prior Opus pricing). Fallback chain conflict resolved: Azure OpenAI Canada region (not US OpenAI) as secondary. Ollama offline tier formally included in cost model and ROI calculation. Technical tradeoffs documented. Opus 4.7 tokenizer inflation risk flagged.

---

## 1. Business Value & ROI

### Quantifiable Benefits

**Developer Productivity Gain**: 20-35% reduction in code review cycle time, translating to $2-4M annually in engineering capacity recovery for a 200-person engineering organization.

**Risk Mitigation**: Centralized governance prevents data leakage incidents that average $4.45M per breach in financial services. PIPEDA compliance enforced as a code invariant, not a policy document.

**Cost Optimization**: Intelligent model routing reduces AI inference costs by 60-80% compared to always using the most expensive model. Key levers:
- Model routing: 70% Haiku ($1/MTok), 25% Sonnet ($3/MTok), 5% Opus ($5/MTok)
- Prompt caching: Up to 90% savings on repeated system prompts (shared PR review templates)
- Batch API: 50% discount for async workloads (nightly evaluations, documentation indexing)
- Ollama Tier 3: $0/MTok for offline and developer local use

**Consolidation Savings**: Eliminating fragmented, one-off AI tools reduces vendor sprawl and maintenance overhead by approximately $500K-800K annually.

### Current Model Pricing (May 2026)

> **Important**: Opus pricing dropped 67% from the prior generation ($15/$75 → $5/$25 per MTok). Any cost models using old pricing significantly overestimate Opus spend.
> **Caution**: Opus 4.7 uses a new tokenizer that generates up to 35% more tokens for the same input. The per-token rate is unchanged but effective cost per request can increase. Apply a 1.35x safety margin in budget pre-flight checks.

| Alias | Active Model | Input $/MTok | Output $/MTok | vs. Prior Gen |
|---|---|---|---|---|
| `haiku` | `claude-haiku-4-5-20251001` | $1.00 | $5.00 | +300% (Haiku 3 was $0.25/$1.25) |
| `sonnet` | `claude-sonnet-4-6` | $3.00 | $15.00 | Unchanged across 4 generations |
| `opus` | `claude-opus-4-7` | $5.00 | $25.00 | -67% (Opus 4.1 was $15/$75) |

Note: Haiku 4.5 is 4x the price of retired Haiku 3, but capability is significantly higher. Routing that previously went to Sonnet can now go to Haiku 4.5 for most simple tasks, preserving cost efficiency.

### Updated Cost Model (500 Developers, 12 Months)

```
Distribution: 70% Haiku, 25% Sonnet, 5% Opus
Daily calls: 500 devs × 20 calls/day = 10,000 calls/day
Avg prompt: 2,000 tokens input, 1,000 tokens output

Daily Cost:
  Haiku  (7,000 calls): 7K × 2K tokens × $1/MTok  + 7K × 1K × $5/MTok    = $14 + $35  = $49
  Sonnet (2,500 calls): 2.5K × 2K × $3/MTok        + 2.5K × 1K × $15/MTok = $15 + $37.50 = $52.50
  Opus     (500 calls): 500 × 2K × $5 × 1.35 margin + 500 × 1K × $25 × 1.35 = $6.75 + $16.88 = $23.63

Total daily: ~$125 → $3,750/month → $45,000/year

With 50% prompt caching on Sonnet (repeated PR review system prompts):
  Savings: ~$315/month → ~$3,780/year

Effective annual LLM cost: ~$41,000 for 500 developers = $82/developer/year
```

**Strategic Returns:**
- Accelerated time-to-market for AI-enabled features
- Platform creates competitive moat through proprietary developer tooling
- Offline capability (Ollama tier) eliminates network-dependency risk

---

## 2. Strategic Alignment

This platform directly supports three enterprise imperatives:

**Operational Excellence**: Standardizes AI adoption across polyglot environments (Ruby, Python, TypeScript, Java/Kotlin), eliminating the "shadow IT" problem where teams deploy ungoverned AI tools that create compliance and security risks.

**Regulatory Compliance**: For Canadian financial services, the governance layer isn't optional — it's mandatory. Centralized data classification ensures RESTRICTED data (customer PII, account data) never leaves Canadian infrastructure. Centralized PII masking, prompt security scanning, and audit trails ensure every AI interaction meets PIPEDA before reaching any external model provider.

**Innovation Velocity**: By providing secure, pre-approved AI capabilities through standardized SDKs, product teams can ship AI features in weeks instead of months, bypassing repetitive security reviews.

---

## 3. Resource Requirements

**Budget**: $1.4M - $1.8M initial investment
- Platform engineering team: 6 FTEs ($1.2M loaded, 12 months)
- Infrastructure: $15-25K/month for model APIs, GPU server (vLLM), observability, cloud hosting
- Hardware: $15-25K one-time for GPU server supporting Tier 2 (vLLM) and enabling Tier 3 development

**Timeline**:
- Phase 1 (Months 1-3): Core gateway, AuthN/AuthZ, Anthropic provider, Ruby SDK
- Phase 2 (Months 4-6): PII masking, async job queue, observability, polyglot SDKs, Azure Canada fallback
- Phase 3 (Months 7-9): vLLM Tier 2, RAG system with provider-agnostic embeddings, eval pipeline
- Phase 4 (Months 10-12): Ollama Tier 3, multi-region, chaos engineering, GA launch

**Team Structure**: 6 FTEs cross-functional platform team reporting to VP Engineering, with dotted-line accountability to CISO for security controls.

---

## 4. Key Decisions Required from Leadership

**Decision 1: Build vs. Buy for Core Gateway** *(Due: Week 2)*
- **Option A (Recommended)**: Build on open-source LiteLLM (routing only) + Presidio (PII) + LLM Guard (injection), orchestrated by Kong/Tyk. Full control. Best for financial services where governance requirements are specific.
- **Option B**: Enterprise LLMOps platform (Portkey, Baseten). Faster to start, less control, higher recurring cost ($60-120K/year licensing), and vendor lock-in.
- **Tradeoff**: Option A requires 3-4 more weeks upfront but avoids recurring $100K+ licensing and builds internal capability.
- **Business Impact**: Option B is faster by 3-4 months; Option A is $300-500K cheaper over 3 years.

**Decision 2: Model Provider Strategy** *(Due: Week 4)*
- **Recommended**: Anthropic primary + Azure OpenAI Canada secondary + vLLM on-prem tertiary + Ollama offline.
- **Not recommended**: US OpenAI as secondary — PIPEDA violation for Canadian customer data.
- **Tradeoff**: Multi-provider adds 6-8 weeks of integration work but eliminates single-provider dependency. Azure Canada adds ~15% cost premium vs. US Azure but is PIPEDA-compliant.

**Decision 3: Governance Enforcement Model** *(Due: Month 2)*
- **Recommendation**: Hard enforcement (HTTP 451) for RESTRICTED data and known PII. Soft enforcement (log + alert) for quality guardrails.
- **Tradeoff**: Hard enforcement reduces liability but increases false-positive friction. Soft enforcement maximizes developer experience but increases compliance risk.

**Decision 4: Platform Funding Model** *(Due: Month 1)*
- Centralized platform cost vs. chargeback to consuming teams.
- **Tradeoff**: Chargeback creates accountability and discourages waste, but adds billing infrastructure complexity and can slow adoption in early months.

**Decision 5: GPU Hardware for Tier 2** *(Due: Month 2)*
- Needed to serve RESTRICTED data on-premises (PIPEDA requirement).
- **Minimum**: 2× A100 80GB or equivalent (supports Llama 3.3 70B at Q4_K_M, ~43GB VRAM)
- **Tradeoff**: $30-50K hardware investment enables RESTRICTED data processing and reduces cloud inference costs by ~40% overall. Without it, RESTRICTED data workloads cannot use AI at all.

---

## 5. Success Criteria

**Operational Metrics (6-month targets)**:
- **Adoption**: 70% of engineering teams actively using platform for at least one use case
- **Reliability**: 99.9% uptime for gateway; <200ms p95 latency overhead
- **Cost Efficiency**: AI spend per developer below $100/6 months ($200/year annualized)
- **Security**: Zero PII leakage incidents; 100% of external AI calls routed through gateway
- **Data Residency**: Zero RESTRICTED data sent to cloud providers (verifiable via audit log `tier` field)

**Business Outcomes (12-month targets)**:
- **Productivity**: 25% reduction in PR-to-merge cycle time for AI-assisted reviews
- **Quality**: 15% reduction in production incidents attributable to code review gaps
- **Compliance**: Pass audit with zero findings on AI governance controls
- **Innovation**: 5+ new AI-enabled features shipped that weren't feasible pre-platform
- **Resilience**: Zero incidents caused by provider outages (fallback chain absorbs all)

**Leading Indicators (Track monthly)**:
- SDK download and usage rates by language and team
- Cost per inference call trending downward
- Developer satisfaction NPS above 40
- Percentage of calls served by Tier 2/3 (target: 20% on-prem/offline for cost and compliance)
- Time from "request platform access" to "first successful API call" under 1 hour

---

## 6. Stakeholder Impact Analysis

**Engineering Teams** (Primary Beneficiaries)
- **Gain**: Friction-free access to AI capabilities including offline mode; faster code reviews; safer experimentation
- **Ask**: Migrate from ad-hoc API keys to standardized SDKs; provide feedback on quality; install IDE plugin
- **Change Management**: Hands-on onboarding, "champion" program in each team, office hours with platform team

**Security & Compliance**
- **Gain**: Centralized audit trail (7-year retention, cryptographically signed); automated PII protection; RESTRICTED data routing enforced in code
- **Ask**: Define acceptable use policies; sign off on PIPEDA compliance approach; review DPA with Anthropic
- **Win**: Platform eliminates 80% of repetitive security reviews for AI features

**Finance**
- **Gain**: Predictable AI cost structure ($82/developer/year at target routing mix); per-team attribution enables chargeback model; real-time budget dashboards
- **Ask**: Approve $1.5M Year 1 investment; approve GPU hardware for Tier 2 ($30-50K)
- **ROI Timeline**: Break-even at month 14; 24x ROI over 3 years

**Product Teams**
- **Gain**: Faster time-to-market for AI features; pre-approved capabilities reduce legal review cycles
- **Ask**: Participate in beta testing (Month 6); specify use cases for platform roadmap

**Executive Leadership**
- **Gain**: Competitive differentiation; PIPEDA compliance embedded in infrastructure; foundation for AI-driven product strategy
- **Ask**: Approve headcount and budget; champion adoption across org; sign off on DPA with Anthropic
- **Strategic Value**: Positions company as AI-forward while maintaining regulatory compliance — critical for fintech credibility

---

## 7. Why This Architecture is Non-Negotiable

The nine architectural components (gateway, AuthN/AuthZ, data classification, async queues, PII masking, observability, evals, polyglot SDKs, provider-agnostic interfaces) aren't gold-plating — they're **load-bearing walls** for enterprise AI:

- **Without the gateway**: No control plane; every team is a compliance risk
- **Without data classification**: RESTRICTED data silently reaches US cloud providers (PIPEDA violation)
- **Without async processing**: Platform breaks under production load on day one (10s webhook vs 60s LLM)
- **Without observability**: Cannot answer "why did costs spike?" or "which team needs help?"
- **Without polyglot SDKs**: Adoption fractures and you're back to ungoverned sprawl within 6 months
- **Without provider-agnostic interfaces**: Provider migrations, model updates, and compliance routing changes require touching application code across N services
- **Without Ollama tier**: AI features are unavailable in air-gapped environments, on flights, and during cloud provider outages

**Bottom Line**: A platform that works 99.5% of the time and violates PIPEDA 0.01% of the time is not acceptable. This architecture makes compliance a code invariant, not a policy aspiration.
