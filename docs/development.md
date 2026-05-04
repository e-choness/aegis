# Development Guide

## Prerequisites

- Docker Desktop (all builds and tests run inside containers — no host Python or Node installs)
- `make`
- An Anthropic API key for integration tests (unit tests run with a dummy key)

## First-Time Setup

```bash
git clone <repo>
cd Aegis

# Create your local env file
cp .env.example .env
# Set ANTHROPIC_API_KEY=sk-ant-... in .env

# Build all images and run tests
make test
```

`make test` runs three suites in sequence:
1. **Gateway** — 112 pytest tests inside `aegis-test:dev`
2. **Python SDK** — 14 pytest tests inside `aegis-sdk-py-test:dev`
3. **TypeScript SDK** — Jest tests inside `aegis-sdk-ts-test:dev`

All tests use mocked external providers — no real API calls are made.

## Running Tests

```bash
make test           # all suites
make test-py        # gateway tests only (fastest feedback loop)
make test-sdk-py    # Python SDK tests only
make test-ts        # TypeScript SDK tests only
```

To pass extra pytest flags:
```bash
docker run --rm -e ANTHROPIC_API_KEY=dummy aegis-test:dev \
  pytest -v -k "test_restricted" --tb=long
```

## Starting the Stack

```bash
make up
```

This starts: `gateway`, `ollama`, `timescaledb`, `vectordb`, `prometheus`, `grafana`.

The gateway won't initialize the RAG service unless `VECTORDB_URL` is set in `.env`:
```bash
VECTORDB_URL=postgresql://aegis:aegis_vec@localhost:5433/aegis_vectors
```

## Project Structure Conventions

| Location | Rule |
|----------|------|
| `src/` | All gateway application code |
| `tests/` | All gateway tests |
| `evals/` | Model evaluation framework |
| `sdk/python/` | Python SDK (separate pyproject.toml, separate Dockerfile) |
| `sdk/typescript/` | TypeScript SDK (separate package.json, separate Dockerfile) |
| `config/` | YAML configuration — no hardcoded model IDs anywhere else |
| `scripts/` | One-shot DB schema scripts |
| `docs/` | Developer documentation |

Files stay under 500 lines. No file should reach this limit; split at the service boundary if approaching it.

## Adding a New LLM Provider

1. Create `src/gateway/providers/<name>_provider.py` implementing `LLMProvider` from `base.py`:

```python
from .base import LLMProvider, CompletionRequest, CompletionResponse

class NewProvider(LLMProvider):
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...
    def estimate_cost_usd(self, input_tokens, output_tokens, alias) -> float: ...
    async def health_check(self) -> bool: ...
```

2. Register it in `src/gateway/providers/factory.py`:

```python
if provider == "newprovider":
    return NewProvider(base_url=os.environ.get("NEW_PROVIDER_URL", "..."))
```

3. Add it to the fallback chain in `src/gateway/services/router.py`:

```python
FALLBACK_CHAIN = [
    ("anthropic",    "tier1_anthropic", 1),
    ("azure_openai", "tier1_azure",     1),
    ("newprovider",  "tier1b_new",      1),   # example: new Tier 1
    ("vllm",         "tier2_vllm",      2),
    ("ollama",       "tier3_ollama",    3),
]
```

4. Add the model IDs and pricing to `config/model_registry.yaml`.

5. Add the provider to `ProviderHealth.__init__` in `src/gateway/services/health.py`.

6. Write tests in `tests/test_<name>_provider.py`. Use `respx` to mock HTTP calls:

```python
import respx, httpx

@respx.mock
@pytest.mark.asyncio
async def test_complete():
    respx.post("http://provider/v1/completions").mock(
        return_value=httpx.Response(200, json={...})
    )
    ...
```

## Adding a New Embedding Provider

1. Create `src/gateway/providers/embeddings/<name>_embedding.py` implementing `EmbeddingProvider`:

```python
from .base import EmbeddingProvider

class NewEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimensions(self) -> int: return 768   # or 1536
```

2. Add a routing case in `src/gateway/providers/embeddings/factory.py`.

3. If the provider serves data outside Canada, it **must not** be returned for `RESTRICTED` or `CONFIDENTIAL` classification. Add a test to `tests/test_embedding_factory.py` that asserts this invariant.

## Adding a New Task Type

In `src/gateway/services/router.py`, add the task to `TASK_ALIAS_MAP`:

```python
TASK_ALIAS_MAP = {
    ...
    "my_new_task": "sonnet",  # or haiku / opus
}
```

Add a test in `tests/test_router.py`:

```python
def test_my_new_task_uses_sonnet():
    config = router.route("my_new_task", "medium", "INTERNAL")
    assert config.alias == "sonnet"
```

## Working with the Eval Framework

The eval framework in `evals/` measures model quality on a labelled dataset before any model change is deployed.

**Running evals** (inject your own `review_fn`):

```python
from evals.runner import run_eval
from evals.scorer import ReviewOutput

async def my_review_fn(diff: str, model_alias: str) -> ReviewOutput:
    # call your model / gateway
    response = await gateway_client.submit_and_poll(diff, "pr_review")
    return ReviewOutput(flags=extract_flags(response))

result = await run_eval("my-model-v2", my_review_fn)
baseline = await run_eval("my-model-v1", baseline_fn)

if not result.beats_baseline(baseline, margin=0.05):
    raise ValueError(f"Model regressed: F1 {result.f1:.3f} vs baseline {baseline.f1:.3f}")
```

**Adding eval cases** — add to `GOLDEN_CASES` in `evals/golden_dataset.py`:

```python
EvalCase(
    id="security-ssrf-002",
    category="security",
    diff="""
+def fetch_url(url):
+    return requests.get(url)  # user-supplied
""",
    expected_flags=["ssrf"],
    expected_severity="high",
    description="SSRF via user-supplied URL in requests.get",
),
```

Cases must belong to one of: `security`, `performance`, `style`, `false_positive`. At least one case from each category must exist (enforced by `test_golden_dataset_has_required_categories`).

**Quality gate**: a new model must beat baseline F1 by ≥5% to be approved for deployment. This threshold is set by `EvalResult.beats_baseline(baseline, margin=0.05)`.

## Model Registry Updates

`config/model_registry.yaml` is the only place model IDs and pricing live. When Anthropic releases a new model:

1. Update the alias entry in `model_registry.yaml`
2. Run `make test-py` — `tests/test_model_registry.py` validates that no retired model IDs remain

Do not hardcode model ID strings anywhere in Python or TypeScript source.

## Database Migrations

**TimescaleDB** (audit log): add SQL to `scripts/init_db.sql`. It runs once on container creation via `docker-entrypoint-initdb.d`. To apply to a running container:

```bash
docker exec -i $(docker compose ps -q timescaledb) \
  psql -U aegis aegis < scripts/init_db.sql
```

**pgvector** (RAG): same pattern with `scripts/init_vectordb.sql` and the `vectordb` container.

## Debugging

```bash
# Tail gateway logs
make logs

# Interactive shell (for manual pytest runs, DB inspection)
make shell

# Check all provider health
curl http://localhost:8000/api/v1/health | jq

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep gateway_requests

# Verify PIPEDA invariant (must always be 0)
curl http://localhost:8000/metrics | grep restricted_data_cloud_violations
```

## Code Style

- Python: no type: ignore, no bare `except`, no `print` (use `logging`)
- No comments that describe what the code does — only comments for non-obvious WHY
- No backwards-compatibility shims — delete unused code
- Validate at system boundaries only (HTTP request bodies); trust internal types
