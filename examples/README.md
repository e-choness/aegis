# Examples

Run any standalone example with Docker Compose (no server, no API keys —
each uses an in-process `FakeProvider`):

    docker compose run --rm dev uv run python examples/01_governed_chat.py

Example index:

| # | Name | Command |
|---|------|---------|
| 01 | Governed chat | `docker compose run --rm dev uv run python examples/01_governed_chat.py` |
| 02 | Vendor-diligence approval flow | `docker compose run --rm dev uv run python examples/scenarios/02_approval_flow.py` *(requires `aegis serve --config examples/fintech.yaml` running — see the script's docstring)* |
| 03 | MCP tool call | `docker compose run --rm dev uv run python examples/03_mcp_tool.py` |
| 04 | RAG | `docker compose run --rm dev uv run python examples/04_rag.py` |
| 05 | Residency | `docker compose run --rm dev uv run python examples/05_residency.py` |

01, 03, 04, and 05 run entirely in-process — no server, no credentials.
02 is the exception: it drives a real `aegis serve` process end to end
(submit → pause → deny → explain → audit export/verify) and is what the
README's demo scenario is built from. `examples/02_approval_flow.py` (no
`scenarios/`) is an older, minimal version of the same idea against the
generic `default` route — kept for reference, but
`examples/scenarios/02_approval_flow.py` is the current, complete one.

`examples/scenarios/` also has its own copies of 01/03/04/05, written
against the SDK talking to a live server rather than an in-process
pipeline — useful once you have `aegis serve` running and want to see the
same requests go through the real HTTP path.
