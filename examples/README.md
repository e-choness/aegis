# Examples

All examples run inside the dev container and need no API keys — every
provider is a `FakeProvider` or a `type: fake` route.

## In-process (no server)

Each script builds a pipeline in memory and runs a request through it.

| # | What it shows | Command |
|---|---|---|
| 01 | PII masking: what the user sent, what the model saw, what came back | `docker compose run --rm dev uv run python examples/01_governed_chat.py` |
| 03 | Governed MCP tool calls: an injected tool result is blocked; a sensitive tool pauses for approval | `docker compose run --rm dev uv run python examples/03_mcp_tool.py` |
| 04 | Governed RAG: a poisoned document is dropped before the model sees the context | `docker compose run --rm dev uv run python examples/04_rag.py` |
| 05 | Residency: the same request allowed, blocked, or paused depending on the endpoint region | `docker compose run --rm dev uv run python examples/05_residency.py` |

## Against a live server

**The approval scenario from the README** — a request is paused by the
residency guardrail, reviewer `jane` denies it, `aegis explain` shows why, and
the exported ledger verifies offline. One command sets up keys, starts
`aegis serve` with [`fintech.yaml`](fintech.yaml), runs the scenario and cleans up:

```bash
docker compose run --rm dev bash scripts/approval-scenario.sh
```

The scenario itself is [`02_approval_flow.py`](02_approval_flow.py); it uses the
Python SDK and the `aegis` CLI against the running server.

## Configs and fixtures

| File | Use |
|---|---|
| [`dev.yaml`](dev.yaml) | Zero-credential local config: fake provider, PII masking, budgets |
| [`fintech.yaml`](fintech.yaml) | The README / approval-scenario config |
| [`aegis.yaml`](aegis.yaml) | A real-provider example (Anthropic + a local OpenAI-compatible model) |
| [`fixtures/`](fixtures/) | Policy fixtures for `aegis policy test examples/fixtures/` |
| [`docs/`](docs/) | Sample documents for the RAG example and `aegis rag index` |
