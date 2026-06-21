# Examples

Run any example with Docker Compose::

    docker compose run --rm dev uv run python examples/01_governed_chat.py

Example index:

| # | Name | Command |
|---|------|---------|
| 01 | Governed chat | `docker compose run --rm dev uv run python examples/01_governed_chat.py` |
| 02 | Approval flow | `docker compose run --rm dev uv run python examples/02_approval_flow.py` *(requires `aegis dev` running)* |
| 03 | MCP tool call | `docker compose run --rm dev uv run python examples/03_mcp_tool.py` |
| 04 | RAG | `docker compose run --rm dev uv run python examples/04_rag.py` |
| 05 | Residency | `docker compose run --rm dev uv run python examples/05_residency.py` |

All examples use the built-in `FakeProvider` — no real API keys required.