# Enterprise AI Developer Platform — Coding Guidelines (.cursorrules)
# Version 2.0 — Updated May 2026

> **What changed in v2**: Model registry updated to current active models. Retired models removed — using old IDs returns HTTP 404 in production. Pricing corrected. `OpenAIEmbedding` hardcoding replaced with provider-agnostic `EmbeddingProvider` interface. Ollama model list updated to current 2026 recommendations. Technical tradeoffs added for all major design decisions.

---

## Project Context

### What We're Building
A production-grade, multi-tenant AI orchestration platform for enterprise software engineering in a regulated financial services environment. This consolidates fragmented AI tooling into secure, governed infrastructure serving 500+ engineers across polyglot codebases (Ruby, Python, TypeScript, Java/Kotlin).

### Strategic Goals
1. **Developer Velocity**: AI-powered PR reviews, deployment checks, code assistance
2. **Enterprise Governance**: PII masking, budget enforcement, audit trails, PIPEDA/GDPR compliance
3. **Cost Optimization**: 60-80% reduction through intelligent model routing
4. **Zero Trust Security**: All LLM interactions mediated through governance gateway
5. **Observability**: Complete cost attribution, quality metrics, distributed tracing

### Core Architectural Principles
- **Gateway as Chokepoint**: 100% of AI traffic routes through centralized governance layer
- **Async-First**: Long-running LLM calls (30-60s) never block HTTP request threads
- **Defense in Depth**: AuthN/AuthZ → data classification → PII scan → prompt injection defense
- **Provider Agnostic**: Abstract ALL external dependencies through interface pattern — application code NEVER references a provider name or model string
- **Fail-Safe Design**: Circuit breakers, graceful degradation, comprehensive retry logic
- **Offline Capable**: Tier 3 (Ollama) provides full functionality with zero network access

---

## Current Model Registry (May 2026)

> **CRITICAL**: The models below are the **only currently active** Anthropic models as of May 2026. All Claude 3.x models and early Claude 4 snapshots are either retired or deprecated. Calling a retired model ID returns HTTP 404.

### Canonical Alias → Provider Model Mapping

```yaml
# gateway/config/model_registry.yaml
# Single source of truth. Application code uses aliases only — NEVER raw provider strings.
# Update this file on model releases; no application code changes required.

models:
  haiku:
    description: "Fast, high-volume tasks: routing, extraction, commit summaries, simple QA"
    cost_per_mtok_input_usd:  1.00     # Updated from $0.25 (Haiku 3, retired Mar 2026)
    cost_per_mtok_output_usd: 5.00     # Updated from $1.25
    context_window_tokens: 200000
    providers:
      tier1_anthropic: "claude-haiku-4-5-20251001"       # Active
      tier1_azure:     "claude-haiku-4-5-20251001"
      tier2_vllm:      "llama3.2:8b-instruct-q5_K_M"
      tier3_ollama:    "qwen2.5:7b"                       # 6GB VRAM, ~50 tok/s RTX 3060

  sonnet:
    description: "Default production tier: PR reviews, RAG responses, code analysis"
    cost_per_mtok_input_usd:  3.00     # Unchanged across 4 generations
    cost_per_mtok_output_usd: 15.00
    context_window_tokens: 1000000     # 1M context at standard pricing (no surcharge)
    providers:
      tier1_anthropic: "claude-sonnet-4-6"               # Active — recommended default
      tier1_azure:     "claude-sonnet-4-6"
      tier2_vllm:      "llama3.3:70b-instruct-q4_K_M"   # 43GB VRAM on vLLM server
      tier3_ollama:    "qwen2.5-coder:32b"               # Best local coding; 22GB VRAM

  opus:
    description: "Premium tier: security audits, multi-file refactoring, architectural analysis"
    cost_per_mtok_input_usd:  5.00     # Down from $15 (Opus 4.1); 67% reduction
    cost_per_mtok_output_usd: 25.00    # Down from $75
    tokenizer_inflation_factor: 1.35   # Opus 4.7 new tokenizer: up to 35% more tokens vs 4.6
    context_window_tokens: 1000000
    providers:
      tier1_anthropic: "claude-opus-4-7"                 # Active flagship (Apr 2026)
      tier1_azure:     "claude-opus-4-6"                 # 4.7 pending Azure availability
      tier2_vllm:      "devstral-small:24b-q5_K_M"      # Best on-prem coding; 16GB VRAM
      tier3_ollama:    "devstral-small:24b-q4_K_M"      # Degrade to sonnet if <24GB VRAM

  local:
    description: "RESTRICTED data only — never routes to cloud providers"
    providers:
      tier2_vllm:   "llama3.3:70b-instruct-q4_K_M"
      tier3_ollama: "llama3.2:8b-instruct-q5_K_M"       # Minimal hardware requirement

embeddings:
  default:
    providers:
      tier1_openai: "text-embedding-3-small"             # 1536-dim; INTERNAL/PUBLIC only
      tier2_vllm:   "bge-m3"                             # 768-dim; on-prem; all classifications
      tier3_ollama: "nomic-embed-text"                   # 768-dim; 274MB; beats ada-002 on retrieval
```

### ⚠️ Retired/Deprecated Model IDs — These Will Fail in Production

| Old ID (DO NOT USE) | Status | Replace With |
|---|---|---|
| `claude-3-haiku-20240307` | **RETIRED** (Mar 2026) | `claude-haiku-4-5-20251001` |
| `claude-3-5-sonnet-20240620` | **RETIRED** | `claude-sonnet-4-6` |
| `claude-3-5-sonnet-20241022` | **RETIRED** | `claude-sonnet-4-6` |
| `claude-3-opus-20240229` | **RETIRED** | `claude-opus-4-7` |
| `claude-opus-4-20250514` | **DEPRECATED** (retiring Jun 2026) | `claude-opus-4-7` |
| `claude-sonnet-4-20250514` | **DEPRECATED** (retiring Jun 2026) | `claude-sonnet-4-6` |

---

## Provider-Agnostic Interface Design

> **Why interfaces are non-negotiable**: Without them, every provider migration, model update, or compliance-driven routing change requires touching application code in N places. With them, the router is the only code that knows which provider is in use — everything else depends on the interface.

### Core Interfaces (Python)

```python
# intelligence/providers/interfaces.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class CompletionRequest:
    prompt: str
    model_alias: str        # Canonical alias: "haiku", "sonnet", "opus", "local"
    max_tokens: int = 2048
    temperature: float = 0.1
    system_prompt: Optional[str] = None

@dataclass
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model_id: str           # Actual provider string — for audit log only
    provider: str           # "anthropic", "vllm", "ollama"
    tier: int               # 1, 2, or 3


class LLMProvider(ABC):
    """
    All completion providers implement this interface.
    Application code depends on LLMProvider — NEVER on concrete classes.

    TRADEOFF — ABC vs Protocol:
    - ABC (chosen): Enforces implementation at class definition; clear missing-method errors.
    - Protocol: Structural subtyping, no inheritance required; more flexible for third-party.
    - Decision: ABC because all providers are internal code under our control.
    """

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, model_alias: str) -> float:
        """Pre-flight budget check. Opus 4.7 applies 1.35x tokenizer safety margin."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def tier(self) -> int: ...


class EmbeddingProvider(ABC):
    """
    Provider-agnostic interface for RAG embeddings.

    CRITICAL ISSUE FIXED: The original codebase hardcoded `OpenAIEmbedding` from LlamaIndex.
    This caused three problems:
    1. RESTRICTED data routed to OpenAI = PIPEDA violation
    2. No fallback if OpenAI goes down
    3. Offline mode impossible

    This interface allows the EmbeddingProviderFactory to route the same way the
    completion router does — classification determines tier, tier determines provider.

    TRADEOFF — vector dimension mismatch:
    OpenAI text-embedding-3-small produces 1536-dim vectors.
    nomic-embed-text and BGE-M3 produce 768-dim vectors.
    You cannot mix them in the same vector DB index.
    Resolution: Maintain a single canonical dimension (768) across all providers.
    Use bge-m3 on-prem and nomic-embed-text offline, both 768-dim.
    OpenAI embeddings (1536-dim) go to a separate index for PUBLIC-only data.
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @property
    @abstractmethod
    def max_chunk_tokens(self) -> int: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def tier(self) -> int: ...


class HealthChecker(ABC):
    """Decouples health-check logic from routing. Mock in tests without network calls."""

    @abstractmethod
    async def is_healthy(self, provider_name: str) -> bool: ...

    @abstractmethod
    async def get_latency_ms(self, provider_name: str) -> Optional[float]: ...
```

### Concrete Provider Implementations

```python
# intelligence/providers/anthropic_provider.py
import anthropic
from .interfaces import LLMProvider, CompletionRequest, CompletionResponse
from ..config import ModelRegistry
from ..secrets import VaultClient

class AnthropicProvider(LLMProvider):
    """
    Tier 1 primary: Anthropic Claude.

    TRADEOFFS:
    + Best quality on complex tasks; 1M context window; extended thinking on Sonnet/Opus
    + Prompt caching: up to 90% savings on repeated system prompts
    + Batch API: 50% discount for async workloads (nightly eval runs)
    - US-based infrastructure: RESTRICTED data MUST NOT reach this provider
    - Opus 4.7 tokenizer generates up to 35% more tokens — budget estimate must include margin
    - Shared infrastructure: rate limits apply per API key
    """

    def __init__(self):
        self.api_key = VaultClient().get_secret("anthropic/api_key")  # Never from os.environ

    @property
    def provider_name(self) -> str: return "anthropic"

    @property
    def tier(self) -> int: return 1

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model_id = ModelRegistry.resolve(request.model_alias, provider="tier1_anthropic")
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(
            model=model_id,
            max_tokens=request.max_tokens,
            messages=[{"role": "user", "content": request.prompt}],
            system=request.system_prompt or "",
        )
        return CompletionResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model_id=model_id, provider=self.provider_name, tier=self.tier,
        )

    async def health_check(self) -> bool:
        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            await client.messages.create(
                model=ModelRegistry.resolve("haiku", provider="tier1_anthropic"),
                max_tokens=1, messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, model_alias: str) -> float:
        pricing = ModelRegistry.get_pricing(model_alias)
        # Opus 4.7 has a new tokenizer that generates up to 35% more tokens for the same text.
        # Apply safety margin so budget pre-flight checks don't underestimate.
        margin = 1.35 if model_alias == "opus" else 1.0
        return (
            input_tokens * margin * pricing["input_per_mtok"] / 1_000_000 +
            output_tokens * margin * pricing["output_per_mtok"] / 1_000_000
        )


# intelligence/providers/vllm_provider.py
import httpx
from .interfaces import LLMProvider, CompletionRequest, CompletionResponse
from ..config import ModelRegistry

class VLLMProvider(LLMProvider):
    """
    Tier 2: On-premises vLLM serving Llama 3.3 70B / Devstral Small 24B.
    Required for RESTRICTED data (PIPEDA compliance).

    TRADEOFFS:
    + Data never leaves your infrastructure; ~$0.10/MTok amortized GPU cost
    + Deterministic: no model updates without your control
    + Can serve RESTRICTED, CONFIDENTIAL, and INTERNAL data
    - Requires GPU hardware: Llama 3.3 70B needs ~43GB VRAM at Q4_K_M
    - Maintenance burden: GPU server management, model updates, HA setup
    - Quality gap vs Anthropic on complex reasoning (not on par with Opus 4.7)
    - Context window limited by available VRAM under load

    RECOMMENDED MODELS on vLLM (2026):
    - General (sonnet-equivalent): llama3.3:70b-instruct-q4_K_M
    - Coding (opus-equivalent):    devstral-small:24b-q5_K_M
    - Fast (haiku-equivalent):     llama3.2:8b-instruct-q5_K_M
    - Embeddings:                  bge-m3 (768-dim, multilingual)
    """

    def __init__(self, endpoint: str = "http://internal-vllm.company.internal:8000"):
        self.endpoint = endpoint

    @property
    def provider_name(self) -> str: return "vllm"

    @property
    def tier(self) -> int: return 2

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model_id = ModelRegistry.resolve(request.model_alias, provider="tier2_vllm")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.endpoint}/v1/chat/completions",
                json={"model": model_id, "messages": [{"role": "user", "content": request.prompt}],
                      "max_tokens": request.max_tokens, "temperature": request.temperature},
            )
            response.raise_for_status()
            data = response.json()
        return CompletionResponse(
            text=data["choices"][0]["message"]["content"],
            input_tokens=data["usage"]["prompt_tokens"],
            output_tokens=data["usage"]["completion_tokens"],
            model_id=model_id, provider=self.provider_name, tier=self.tier,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.endpoint}/health")
                return r.status_code == 200
        except Exception:
            return False

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, model_alias: str) -> float:
        return (input_tokens + output_tokens) * 0.10 / 1_000_000  # Amortized GPU cost


# intelligence/providers/ollama_provider.py
import ollama as ollama_client
from .interfaces import LLMProvider, CompletionRequest, CompletionResponse
from ..config import ModelRegistry

class OllamaProvider(LLMProvider):
    """
    Tier 3: Local Ollama. Zero network dependency. Always available.

    TRADEOFFS:
    + No network required; free to operate; works in air-gapped environments
    + Model pulled once, runs offline indefinitely — no silent model updates
    + nomic-embed-text outperforms OpenAI ada-002 on standard retrieval benchmarks
    - Quality gap vs frontier models (especially complex multi-step reasoning)
    - GPU required for usable performance on 32B models
    - No SLA, no support contract, no managed updates

    CURRENT RECOMMENDED MODELS (May 2026):
    Pull with: ollama pull <model_name>

    General:
      qwen2.5:7b            — 6GB VRAM, good all-rounder, 50+ tok/s on RTX 3060
      llama3.2:8b           — proven, reliable, excellent instruction following

    Coding (recommended for PR review in offline mode):
      qwen2.5-coder:32b    — 22GB VRAM, 77%+ HumanEval, best local code model
      devstral-small:24b   — 16GB VRAM, agentic coding, multi-file edits
      codestral:22b        — fill-in-the-middle support, good for autocomplete

    Reasoning / Debugging:
      deepseek-r1:14b      — chain-of-thought, shows its reasoning, best local debugger

    Lightweight (any hardware):
      qwen2.5:3b           — CPU-viable, minimal VRAM
      phi-4:3.8b           — punches above weight, good for constrained environments

    Embeddings:
      nomic-embed-text     — 274MB, 768-dim, standard RAG choice, beats ada-002
      mxbai-embed-large    — alternative 1024-dim option for higher representational capacity
    """

    def __init__(self, host: str = "http://localhost:11434"):
        self.client = ollama_client.Client(host=host)

    @property
    def provider_name(self) -> str: return "ollama"

    @property
    def tier(self) -> int: return 3

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        model_id = ModelRegistry.resolve(request.model_alias, provider="tier3_ollama")
        response = self.client.chat(
            model=model_id,
            messages=[{"role": "user", "content": request.prompt}],
            options={"num_predict": request.max_tokens, "temperature": request.temperature},
        )
        return CompletionResponse(
            text=response["message"]["content"],
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            model_id=model_id, provider=self.provider_name, tier=self.tier,
        )

    async def health_check(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, model_alias: str) -> float:
        return 0.0  # No per-token cost
```

### Provider-Agnostic Embedding Implementations

```python
# intelligence/providers/embeddings/factory.py
from ..interfaces import EmbeddingProvider
from .openai_embedding import OpenAIEmbeddingProvider
from .vllm_embedding import VLLMEmbeddingProvider
from .ollama_embedding import OllamaEmbeddingProvider

class EmbeddingProviderFactory:
    """
    Selects the embedding provider based on data classification and health.

    DIMENSION COMPATIBILITY NOTE:
    - OpenAI: 1536-dim — use a separate vector DB index
    - vLLM/BGE-M3 + Ollama/nomic-embed-text: both 768-dim — same index
    The factory enforces this: RESTRICTED/CONFIDENTIAL data always routes to 768-dim providers.
    """

    @staticmethod
    def get(data_classification: str, health_checker) -> EmbeddingProvider:
        if data_classification == "RESTRICTED":
            # Must stay on-prem
            if health_checker.is_healthy("vllm"):
                return VLLMEmbeddingProvider()
            return OllamaEmbeddingProvider()  # Always available

        if data_classification in ("CONFIDENTIAL", "INTERNAL"):
            if health_checker.is_healthy("vllm"):
                return VLLMEmbeddingProvider()
            # OpenAI is acceptable for INTERNAL (not customer data)
            if health_checker.is_healthy("openai"):
                return OpenAIEmbeddingProvider()
            return OllamaEmbeddingProvider()

        # PUBLIC data — cheapest/fastest option
        if health_checker.is_healthy("openai"):
            return OpenAIEmbeddingProvider()
        return OllamaEmbeddingProvider()


# intelligence/providers/embeddings/ollama_embedding.py
import ollama as ollama_client
from ..interfaces import EmbeddingProvider

class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    nomic-embed-text via Ollama.
    Safe for ALL data classifications. Pull: ollama pull nomic-embed-text

    TRADEOFFS:
    + 274MB model — negligible VRAM overhead alongside a larger chat model
    + Outperforms OpenAI text-embedding-ada-002 on both short and long retrieval benchmarks
    + 768-dim matches vLLM/BGE-M3 — compatible index schema
    - 768-dim vs OpenAI 1536-dim — slightly less representational capacity for very long docs
    - Must have Ollama running locally; not a managed service
    """

    def __init__(self, host: str = "http://localhost:11434"):
        self.client = ollama_client.Client(host=host)
        self._model = "nomic-embed-text"

    @property
    def dimensions(self) -> int: return 768
    @property
    def max_chunk_tokens(self) -> int: return 8192
    @property
    def provider_name(self) -> str: return "ollama"
    @property
    def tier(self) -> int: return 3

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.client.embeddings(model=self._model, prompt=t)["embedding"] for t in texts]

    async def embed_single(self, text: str) -> list[float]:
        return self.client.embeddings(model=self._model, prompt=text)["embedding"]
```

### Smart Model Router

```python
# intelligence/router.py
from dataclasses import dataclass
from .providers.factory import ProviderFactory
from .config import ModelRegistry

@dataclass
class ModelConfig:
    provider: str
    model_alias: str
    tier: int

class ModelRouter:
    """
    TRADEOFF — Rules-based vs ML-based routing:
    Rules-based (chosen): Deterministic, auditable, testable. A misrouting bug is
    immediately visible in code. Critical for compliance — we cannot have an ML model
    accidentally routing RESTRICTED data to cloud.
    ML-based: Could auto-optimize cost/quality thresholds over time, but opaque.
    Decision: Rules-based now; ML routing for non-compliance decisions in future phase.
    """

    FALLBACK_CHAIN = [
        ("anthropic",    "tier1_anthropic"),
        ("azure_openai", "tier1_azure"),
        ("vllm",         "tier2_vllm"),
        ("ollama",       "tier3_ollama"),   # Always available — no network required
    ]

    def __init__(self, health_checker):
        self.health_checker = health_checker

    def route(self, task_type: str, complexity: str, data_classification: str,
              budget_remaining_usd: float = float("inf")) -> ModelConfig:

        # RULE 1: RESTRICTED data never reaches cloud — enforced in code, not policy
        if data_classification == "RESTRICTED":
            return self._select_onprem("local")

        # RULE 2: Budget-aware degradation (prevents runaway costs)
        alias = self._select_alias(task_type, complexity)
        if alias == "opus" and budget_remaining_usd < 1.00:
            alias = "sonnet"

        return self._select_tier(alias)

    def _select_alias(self, task_type: str, complexity: str) -> str:
        # Haiku: 5x cheaper than sonnet — use aggressively for simple tasks
        if task_type in ("commit_summary", "simple_qa", "classification", "routing"):
            return "haiku"
        # Opus: highest reasoning — only when genuinely needed
        if task_type in ("security_audit", "architecture_review") and complexity == "high":
            return "opus"
        return "sonnet"  # Default for PR reviews, RAG, documentation

    def _select_tier(self, alias: str) -> ModelConfig:
        for provider_name, tier_key in self.FALLBACK_CHAIN:
            if self.health_checker.is_healthy(provider_name):
                model_id = ModelRegistry.resolve(alias, provider=tier_key)
                if model_id:
                    tier_num = int(tier_key.split("_")[0].replace("tier", ""))
                    return ModelConfig(provider=provider_name, model_alias=alias, tier=tier_num)
        raise AllProvidersDownError("All providers exhausted in fallback chain")

    def _select_onprem(self, alias: str) -> ModelConfig:
        if self.health_checker.is_healthy("vllm"):
            return ModelConfig(provider="vllm", model_alias=alias, tier=2)
        return ModelConfig(provider="ollama", model_alias=alias, tier=3)
```

---

## Code Style & Patterns

### File Structure (Monorepo)

```
ai-platform/
├── gateway/                       # Ruby on Rails
│   ├── app/controllers/api/v1/
│   ├── app/services/
│   ├── app/jobs/
│   └── config/
│       └── model_registry.yaml    # ← SINGLE SOURCE OF TRUTH for model IDs
├── intelligence/                  # Python
│   ├── providers/
│   │   ├── interfaces.py          # LLMProvider, EmbeddingProvider, HealthChecker
│   │   ├── anthropic_provider.py
│   │   ├── vllm_provider.py
│   │   ├── ollama_provider.py
│   │   ├── azure_openai_provider.py
│   │   ├── factory.py
│   │   └── embeddings/
│   │       ├── openai_embedding.py
│   │       ├── vllm_embedding.py
│   │       ├── ollama_embedding.py
│   │       └── factory.py         # ← EmbeddingProviderFactory
│   ├── router.py                  # ModelRouter + ModelConfig
│   ├── prompt_templates/
│   ├── rag/
│   └── evals/
├── sdk/
│   ├── ruby/
│   ├── python/
│   ├── typescript/
│   └── kotlin/
└── docs/adr/                      # Architecture Decision Records
```

### Naming Conventions
- **Interfaces**: `<Domain>Provider` (e.g., `LLMProvider`, `EmbeddingProvider`)
- **Concrete classes**: `<ProviderName>Provider` (e.g., `AnthropicProvider`, `OllamaEmbeddingProvider`)
- **Services**: `<Domain>Orchestrator`, `<Domain>Service`
- **Jobs**: `<Action>Job`
- **API Endpoints**: `/api/v1/<resource>` (versioned from day 1)
- **Model references in code**: ALWAYS canonical alias (`"haiku"`, `"sonnet"`, `"opus"`, `"local"`) — NEVER provider strings

### Ruby/Rails: Async Job Processing (MANDATORY)

```ruby
# CORRECT: Async — job queue absorbs the 30-60s LLM call
class PrReviewOrchestrator
  def execute
    PrReviewJob.perform_async(
      pr_id: @pull_request.id,
      diff_url: @pull_request.diff_url,
      team_id: @team.id,
      trace_id: SecureRandom.uuid
    )
  end
end

class PrReviewJob < ApplicationJob
  sidekiq_options retry: 3, queue: :ai_inference
  retry_on ExternalAPIError, wait: :exponentially_longer, attempts: 3
  discard_on DataClassificationViolation

  def perform(pr_id:, diff_url:, team_id:, trace_id:)
    OpenTelemetry.tracer.in_span("pr_review_job", attributes: { trace_id: trace_id }) do
      diff       = GitHubClient.fetch_diff(diff_url)
      review     = AIGatewayClient.review_code(diff: diff, team_id: team_id)
      GitHubClient.post_review(pr_id, review)
      CostTracker.record(team_id: team_id, cost: review.cost_usd, model: review.model_alias)
    end
  rescue => e
    ErrorTracker.notify(e, context: { pr_id: pr_id, trace_id: trace_id })
    raise
  end
end

# WRONG: Synchronous — will timeout at GitHub's 10-second webhook deadline
def create
  result = LLMClient.call(params[:prompt])  # NEVER DO THIS
  render json: result
end
```

### TypeScript SDK Error Handling

```typescript
export class AIPlatformClient {
  async reviewCode(diff: string, options?: ReviewOptions): Promise<Review> {
    try {
      return (await this.httpClient.post('/api/v1/inference', {
        task_type: 'pr_review', prompt: diff, ...options,
      })).data;
    } catch (error) {
      switch (error.response?.status) {
        case 429: throw new RateLimitError(`Retry after ${error.response.headers['retry-after']}s`);
        case 402: throw new BudgetExceededError('Monthly AI budget exhausted');
        case 503: throw new ModelUnavailableError('All providers temporarily down');
        case 451: throw new DataResidencyError('RESTRICTED data blocked by compliance router');
        default:  throw new AIPlatformError(`Unexpected error: ${error.message}`);
      }
    }
  }
}
```

---

## Critical DO's and DON'Ts

### ✅ ALWAYS DO

1. **Depend on the interface, not the implementation**
   ```python
   # CORRECT — testable, swappable, provider-agnostic
   async def process(provider: LLMProvider, request: CompletionRequest) -> str:
       response = await provider.complete(request)
       return response.text

   # WRONG — locked to Anthropic; cannot mock; cannot failover
   async def process(prompt: str) -> str:
       return anthropic.messages.create(model="claude-sonnet-4-6", ...)
   ```

2. **Use `EmbeddingProviderFactory`, never hardcoded embedding classes**
   ```python
   # CORRECT — PIPEDA-safe, falls back automatically
   provider = EmbeddingProviderFactory.get(data_classification, health_checker)
   vectors = await provider.embed(chunks)

   # WRONG — PIPEDA violation for RESTRICTED data; no fallback if OpenAI down
   from llama_index.embeddings import OpenAIEmbedding
   embedding = OpenAIEmbedding(model="text-embedding-3-small")
   ```

3. **Use canonical model aliases everywhere — never raw provider strings**
   ```python
   # CORRECT — one YAML update handles all model renames
   model_config = router.route(task_type="code_review", ...)
   result = await provider.complete(CompletionRequest(model_alias="sonnet", ...))

   # WRONG — breaks when Anthropic releases next version
   provider.complete("claude-sonnet-4-6", prompt)
   ```

4. **Apply Opus 4.7 tokenizer safety margin in cost estimates**
   ```python
   # Opus 4.7 new tokenizer can produce up to 35% more tokens for the same text.
   # A 1M-token request on Opus 4.7 can cost as much as a 1.35M-token request on 4.6.
   margin = 1.35 if model_alias == "opus" else 1.0
   estimated_cost = input_tokens * margin * pricing["input"] / 1_000_000
   ```

5. **Fetch all secrets from Vault — never from environment variables**
6. **Log every inference with team ID, model alias, provider, tier, cost, and trace ID**
7. **Classify data before routing — routing is a consequence of classification**
8. **Implement circuit breakers for all external services**

### ❌ NEVER DO

1. Instantiate `AnthropicProvider` directly in business logic — use `ProviderFactory`
2. Reference `claude-haiku-4-5-20251001` or any provider model string in application code
3. Use `OpenAIEmbedding` from LlamaIndex without going through `EmbeddingProviderFactory`
4. Allow `data_classification == "RESTRICTED"` to reach `AnthropicProvider` or `AzureOpenAIProvider`
5. Make synchronous LLM calls from HTTP handlers
6. Send raw prompts to any provider without PII scanning first

---

## Technical Tradeoffs Reference

| Decision | Choice | Upside | Downside | Alternative |
|---|---|---|---|---|
| Provider abstraction | `ABC` interface | Enforced contract, clear errors | No structural subtyping | `Protocol` (flexible, less strict) |
| Embedding fallback | `EmbeddingProviderFactory` | PIPEDA-safe, no hardcoding | More code, dimension mismatch risk | Hardcode OpenAI (simpler, breaks offline) |
| Model routing | Rules-based | Auditable, deterministic, testable | Manual threshold tuning | ML-based (adaptive but opaque, compliance risk) |
| Opus 4.7 cost guard | 1.35x safety margin | Prevents budget overrun | Slight over-estimation | Exact pre-flight tokenization (slow) |
| Async queue | Sidekiq + Celery | Proven, retries, dead-letter queue | Two systems in polyglot env | Temporal (powerful, higher ops overhead) |
| Tier 3 offline model | Ollama (qwen2.5, nomic-embed-text) | Zero network, free, dev-friendly | VRAM needed for 32B models | No offline tier (simpler, PIPEDA risk in air-gap) |
| Embedding dimensions | 768-dim (BGE-M3/nomic) as canonical | Consistent index schema across tiers | Less capacity than 1536-dim OpenAI | Two indices by tier (complex, expensive) |

---

## Requirements & Acceptance Criteria

### Functional Requirements

**FR-1: Automated PR Code Review**
- Given: Developer opens PR with 10-500 lines changed
- When: PR contains security-critical code (auth, payments, database)
- Then: System posts inline review within 90 seconds using `sonnet` alias by default
- Acceptance: 95% of known security issues caught; <5% false positive rate

**FR-2: Cost-Aware Model Routing**
- Given: Team has $500/month AI budget
- When: Team submits 1,000 inference requests
- Then: System routes to minimize cost (target: 70% haiku, 25% sonnet, 5% opus)
- Acceptance: Budget not exceeded; quality within 5% of all-sonnet baseline

**FR-3: PII Protection**
- Given: Prompt contains Canadian SIN, credit card, or email
- When: Request reaches gateway
- Then: PII masked before any provider call; unmasked in response; incident logged
- Acceptance: 100% detection of known PII patterns

**FR-4: Data Residency Compliance**
- Given: Prompt is classified RESTRICTED
- When: Router selects provider
- Then: Only `VLLMProvider` (tier 2) or `OllamaProvider` (tier 3) selected
- Acceptance: Zero RESTRICTED data logged to `AnthropicProvider` or `AzureOpenAIProvider`

**FR-5: Offline Mode**
- Given: Network is unavailable
- When: Any inference request arrives
- Then: `OllamaProvider` serves the request with locally-pulled models
- Acceptance: Full PR review functionality with 0% cloud API calls

### Non-Functional Requirements

| Requirement | Target | Measurement |
|---|---|---|
| Gateway overhead | <20ms p99 | OpenTelemetry spans |
| End-to-end PR review | <60s p95 | Job queue completion time |
| RAG query | <3s p99 | Trace end-to-end |
| Gateway uptime | 99.9% | Health check pings |
| Cost per developer | <$322/year | TimescaleDB attribution |
| PII detection rate | 100% of known patterns | Synthetic test suite |

---

## Testing Requirements

```python
def test_restricted_routes_to_onprem_only():
    """RESTRICTED data must NEVER reach cloud providers — verified by unit test."""
    mock_health = Mock()
    mock_health.is_healthy.return_value = True
    router = ModelRouter(health_checker=mock_health)

    config = router.route("code_review", "high", data_classification="RESTRICTED")

    assert config.provider in ("vllm", "ollama")
    assert config.tier >= 2

def test_ollama_final_fallback():
    """Ollama must serve requests even when all cloud and vLLM are down."""
    mock_health = Mock()
    mock_health.is_healthy.side_effect = lambda p: p == "ollama"
    router = ModelRouter(health_checker=mock_health)

    config = router.route("commit_summary", "low", data_classification="INTERNAL")

    assert config.provider == "ollama"
    assert config.tier == 3

def test_embedding_restricted_never_openai():
    """RESTRICTED data embedding must never go to OpenAI."""
    mock_health = Mock()
    mock_health.is_healthy.return_value = True
    provider = EmbeddingProviderFactory.get("RESTRICTED", mock_health)

    assert not isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.tier >= 2

def test_opus_cost_estimate_includes_tokenizer_margin():
    """Opus 4.7 tokenizer can generate up to 35% more tokens — budget check must account for this."""
    provider = AnthropicProvider.__new__(AnthropicProvider)
    cost = provider.estimate_cost_usd(1_000_000, 200_000, "opus")
    # Without margin: (1M * $5 + 200K * $25) / 1M = $10.00
    # With 1.35x margin: $13.50
    assert cost == pytest.approx(13.50, rel=0.01)

def test_retired_model_id_not_in_registry():
    """Ensure retired model IDs are not present anywhere in the model registry."""
    registry_content = open("gateway/config/model_registry.yaml").read()
    retired = [
        "claude-3-haiku-20240307",
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
    ]
    for model_id in retired:
        assert model_id not in registry_content, f"RETIRED model {model_id} found in registry"
```

---

## Observability

```yaml
# Required Prometheus metrics
gateway_requests_total{team_id, model_alias, provider, tier, status}
gateway_latency_seconds{endpoint, percentile}
inference_cost_usd_total{team_id, model_alias, provider, tier}
pii_detections_total{severity, entity_type}
budget_utilization_ratio{team_id}          # Alert at 0.7 and 0.9
circuit_breaker_state{provider}            # 0=closed, 1=half-open, 2=open
provider_health{provider, tier}            # 0=unhealthy, 1=healthy
embedding_provider_latency_ms{provider}
```

---

## Security & Compliance

### Data Classification

```python
class DataClassifier:
    """
    TRADEOFF — regex vs ML classifier:
    Regex (chosen now): <1ms, auditable, zero false negatives on known patterns.
    ML classifier: Catches obfuscated PII but adds 20-50ms latency.
    Recommendation: Add ML classifier as secondary pass in Phase 3.
    """

    PATTERNS = {
        "RESTRICTED": [
            r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",    # Canadian SIN
            r"\b(?:\d{4}[-\s]?){4}\b",               # Credit card
            r"\baccount[_-]?number\b",
        ],
        "CONFIDENTIAL": [
            r"[a-zA-Z0-9._%+-]+@(?:wealthsimple|company)\.com",
            r"\bapi[_-]?key\b",
            r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
        ],
    }

    def classify(self, text: str) -> str:
        for level in ("RESTRICTED", "CONFIDENTIAL"):
            if any(re.search(p, text, re.I) for p in self.PATTERNS[level]):
                return level
        return "INTERNAL"
```

### Audit Trail

```sql
CREATE TABLE inference_audit_log (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id        UUID NOT NULL,
    team_id        UUID NOT NULL,
    model_alias    VARCHAR(20)  NOT NULL,    -- 'haiku', 'sonnet', 'opus', 'local'
    model_id       VARCHAR(100) NOT NULL,    -- Actual provider string — for audit only
    provider       VARCHAR(50)  NOT NULL,    -- 'anthropic', 'vllm', 'ollama'
    tier           INTEGER      NOT NULL,    -- 1=cloud, 2=on-prem, 3=offline
    data_class     VARCHAR(20)  NOT NULL,    -- 'RESTRICTED', 'CONFIDENTIAL', 'INTERNAL'
    prompt_hash    CHAR(64)     NOT NULL,    -- SHA-256; NEVER store raw prompt
    cost_usd       DECIMAL(10,6),
    latency_ms     INTEGER,
    trace_id       UUID NOT NULL
    -- Retention: 90 days hot (TimescaleDB), 7 years cold (S3 Object Lock)
);
```

---

## Architecture Decision Records

**ADR-001: Three-Tier Provider Model**
- Tier 1 (Cloud): Anthropic (primary), Azure OpenAI Canada (secondary — PIPEDA-safe)
- Tier 2 (On-prem): vLLM for RESTRICTED data
- Tier 3 (Offline): Ollama — always available
- Rationale: PIPEDA compliance + resilience + offline capability

**ADR-002: Canonical Model Registry**
- Single YAML maps aliases to provider strings
- Rationale: Anthropic has changed naming three times since 2024. One file update vs 50+ code changes.

**ADR-003: `LLMProvider` + `EmbeddingProvider` ABC interfaces**
- All provider access through abstract interfaces
- Rationale: Testability, provider swaps, compliance enforcement as code invariant

**ADR-004: Async-First**
- ALL LLM calls via Sidekiq/Celery
- Rationale: GitHub webhook timeout 10s; Claude Sonnet PR review 30-60s

**ADR-005: Classification Before Routing**
- Classification runs first; routing is a consequence
- Rationale: PIPEDA compliance enforced in code, not policy documents

**ADR-006: Rules-Based Routing**
- Deterministic, auditable, testable
- Rationale: ML routing risks opaque RESTRICTED-data misclassification

**ADR-007: Opus 4.7 Tokenizer Safety Margin**
- 1.35x multiplier on Opus cost estimates
- Rationale: New tokenizer generates up to 35% more tokens; without margin, budget checks underestimate
