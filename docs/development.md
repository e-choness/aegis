# Development Guide

> Everything runs inside Docker. No host Python or Node installs required.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [First-Time Setup](#first-time-setup)
- [Daily Workflow](#daily-workflow)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [Adding a Provider](#adding-a-provider)
- [Adding an Embedding Provider](#adding-an-embedding-provider)
- [Extending the Model Registry](#extending-the-model-registry)
- [Adding API Endpoints](#adding-api-endpoints)
- [Working with the SDKs](#working-with-the-sdks)
- [Running Evals](#running-evals)
- [Linting & Formatting](#linting--formatting)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Docker Desktop** — all builds and tests run inside containers
- **Make** — task runner (`make build`, `make test`, etc.)
- An `ANTHROPIC_API_KEY` for cloud inference (Ollama-only mode works without one)

No host Python, Node, or database installs needed.

---

## First-Time Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> aegis
cd aegis

# 2. Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 3. Build images and run tests
make test
# Expected: 103 passed in ~2s

# 4. Start the full stack
make up
# Gateway:    http://localhost:8000
# Swagger UI: http://localhost:8000/docs
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001 (admin / admin)
```

---

## Daily Workflow

```bash
# Start services (skips rebuild if images are current)
make up

# Tail gateway logs
make logs

# Run all tests
make test

# Open a shell inside the gateway container
make shell

# Stop everything
make down
```

---

## Running Tests

All 103 tests run inside Docker — the test profile builds an isolated image with `pytest` and all dev dependencies:

```bash
make test
# Equivalent to: docker compose --profile test run --rm test
```

### Run a single test file

```bash
docker compose --profile test run --rm test pytest tests/test_router.py -v
```

### Run a single test

```bash
docker compose --profile test run --rm test pytest tests/test_router.py::test_restricted_routing_invariant -v
```

### Key test files

| File | What it covers |
|------|---------------|
| `tests/test_router.py` | Routing invariants, budget degradation, PIPEDA |
| `tests/test_classifier.py` | Data classification patterns |
| `tests/test_pii.py` | Mask/unmask correctness |
| `tests/test_embedding_factory.py` | Embedding provider routing, PIPEDA for embeddings |
| `tests/test_audit.py` | Audit log writes, tier tracking |
| `tests/test_budget.py` | Per-team cap enforcement |
| `tests/test_rag.py` | RAG classification-aware retrieval |
| `tests/test_inference.py` | End-to-end pipeline (mocked providers) |

---

## Project Structure

```
src/gateway/
├── main.py                    # FastAPI app, lifespan, middleware, router registration
├── models.py                  # Pydantic request/response models
├── api/v1/
│   ├── inference.py           # POST /inference, GET /jobs/{id}
│   ├── health.py              # GET /health
│   └── rag.py                 # POST /rag/index, POST /rag/query
├── providers/
│   ├── base.py                # LLMProvider ABC
│   ├── factory.py             # ProviderFactory.get(name) → LLMProvider
│   ├── anthropic_provider.py
│   ├── azure_openai_provider.py
│   ├── ollama_provider.py
│   └── embeddings/
│       ├── base.py            # EmbeddingProvider ABC
│       ├── factory.py         # EmbeddingProviderFactory.get(classification)
│       ├── ollama_embedding.py
│       └── openai_embedding.py
└── services/
    ├── classifier.py          # DataClassifier — regex patterns
    ├── router.py              # ModelRouter — deterministic routing
    ├── pii.py                 # PIIMasker — Presidio + CA_SIN
    ├── inference.py           # InferenceService — pipeline orchestrator
    ├── rag.py                 # TextChunker + RAGService
    ├── audit.py               # AuditLogger → TimescaleDB
    ├── budget.py              # BudgetService — per-team caps
    └── health.py              # ProviderHealth — circuit breaker
```

---

## Adding a Provider

1. **Create the provider class** in `src/gateway/providers/`:

```python
# src/gateway/providers/my_provider.py
from .base import LLMProvider

class MyProvider(LLMProvider):
    async def complete(self, prompt: str, model_id: str, max_tokens: int) -> str:
        # call the API
        ...

    async def health_check(self) -> bool:
        ...
```

2. **Register it in the factory** (`src/gateway/providers/factory.py`):

```python
from .my_provider import MyProvider

class ProviderFactory:
    @staticmethod
    def get(name: str) -> LLMProvider:
        match name:
            case "my_provider": return MyProvider()
            ...
```

3. **Add it to the health tracker** (`src/gateway/services/health.py`):

```python
self._healthy = {
    "anthropic": False,
    "azure_openai": False,
    "my_provider": False,   # add here
    "ollama": True,
}
```

4. **Add it to the fallback chain** (`src/gateway/services/router.py`):

```python
FALLBACK_CHAIN = [
    ("anthropic",    "tier1_anthropic", 1),
    ("my_provider",  "tier1_my",        1),   # add here
    ("ollama",       "tier3_ollama",    3),
]
```

5. **Add model IDs to the registry** (`config/model_registry.yaml`):

```yaml
sonnet:
  tier1_my: "my-model-id-v1"
  ...
```

6. **Write tests** covering health fallback and PIPEDA invariant if the provider is cloud-hosted.

---

## Adding an Embedding Provider

1. **Create the class** in `src/gateway/providers/embeddings/`:

```python
from .base import EmbeddingProvider

class MyEmbeddingProvider(EmbeddingProvider):
    dimensions = 1024  # declare the output dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    async def health_check(self) -> bool:
        ...
```

2. **Register it in** `src/gateway/providers/embeddings/factory.py` following the existing classification routing logic.

3. **If the provider is cloud-hosted**, add a test in `tests/test_embedding_factory.py` asserting it is never selected for `RESTRICTED` or `CONFIDENTIAL` data.

4. **Note the dimensions.** If different from 768, a new pgvector table and index will be needed (see `scripts/init_vectordb.sql`).

---

## Extending the Model Registry

`config/model_registry.yaml` controls all model IDs and costs. Never hardcode model IDs in Python.

```yaml
# Add a new alias
my_alias:
  tier1_anthropic: "claude-new-model-id"
  tier3_ollama:    "my-local-model:7b"
  cost_input_per_mtok:  2.00
  cost_output_per_mtok: 10.00
  context_tokens:  200000
```

Then map task types to the alias in `ModelRouter.TASK_ALIAS_MAP`:

```python
TASK_ALIAS_MAP = {
    "my_task": "my_alias",
    ...
}
```

---

## Adding API Endpoints

1. Create a router file in `src/gateway/api/v1/`
2. Define request/response Pydantic models
3. Register the router in `src/gateway/main.py`:

```python
from .api.v1.my_feature import router as my_router
app.include_router(my_router)
```

4. Add tests in `tests/`

---

## Working with the SDKs

### Python SDK

```bash
# Install in development mode (from inside the gateway container)
pip install -e sdk/python

# Run SDK tests
pytest sdk/python/tests/
```

### TypeScript SDK

```bash
cd sdk/typescript
npm install
npm test
npm run build
```

---

## Running Evals

The `evals/` directory contains evaluation harnesses for testing model quality on task-specific benchmarks.

```bash
# Run all evals (requires gateway running)
docker compose --profile test run --rm test python -m evals.run

# Run a specific eval
docker compose --profile test run --rm test python -m evals.run --task security_audit
```

---

## Linting & Formatting

```bash
# Inside the gateway container
make shell

# Format
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

---

## Troubleshooting

### Gateway returns 503 on RAG endpoints

`VECTORDB_URL` is not set or TimescaleDB is not healthy. Check:

```bash
make logs
# Look for: "VECTORDB_URL not set — RAG service disabled"
# or: asyncpg connection errors
```

Ensure `VECTORDB_URL=postgresql://aegis:aegis_dev@timescaledb:5432/aegis` is in your `.env`.

### Embedding calls fail with connection error

`nomic-embed-text` model needs to be available in Ollama. The provider will auto-pull it on first use, but this requires Ollama to be running and reachable at `OLLAMA_BASE_URL`.

```bash
# Check Ollama is up
curl http://localhost:11434/api/tags
```

### Tests fail with import errors

The test image may be stale. Force a rebuild:

```bash
make build
make test
```

### `restricted_data_cloud_violations_total` is non-zero

This is a CRITICAL compliance violation. Immediately:

1. Stop the gateway: `make down`
2. Check `make logs` for the offending request
3. Audit `tests/test_router.py::test_restricted_routing_invariant`
4. Verify `ModelRouter.route()` returns Ollama for all RESTRICTED inputs

Do not restart until the root cause is identified and fixed.
