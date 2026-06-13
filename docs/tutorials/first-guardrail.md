# Tutorial: Write your first guardrail

This tutorial walks you through creating a custom guardrail plugin, testing it
with the contract test kit, and wiring it into an Aegis pipeline.

## Scaffold the plugin

```bash
aegis plugin scaffold guardrail my-guard
```

This creates a publishable Python package at `./aegis-guardrail-my-guard/` with:

- `src/aegis_guardrail_my_guard/guard.py` — the guardrail implementation
- `tests/test_my_guard.py` — contract tests using `GuardrailContractKit`
- `pyproject.toml` with the `aegis.guardrails` entry point declared

## Implement the guardrail

Open `src/aegis_guardrail_my_guard/guard.py`. The scaffold generates a working
`RegexGuard`-style skeleton. Replace the pattern with your logic:

```python
from typing import ClassVar, Literal

from aegis_core.pipeline import RunState, Verdict


class KeywordGuard:
    """Blocks messages containing a configurable keyword list."""

    streaming: ClassVar[Literal["none"]] = "none"
    name = "keyword-guard"

    def __init__(self, keywords: list[str]) -> None:
        self._keywords = [kw.lower() for kw in keywords]

    async def scan(self, messages: list[dict], state: RunState) -> Verdict:
        text = " ".join(m.get("content", "") for m in messages).lower()
        for kw in self._keywords:
            if kw in text:
                return Verdict.block(f"Blocked keyword: {kw!r}")
        return Verdict.allow()
```

!!! note
    `Verdict.block()`, `Verdict.allow()`, `Verdict.sanitize()`, and
    `Verdict.require_approval()` are the four verdict factories.

## Run the contract tests

```bash
cd aegis-guardrail-my-guard
pytest -q
```

The `GuardrailContractKit` tests verify your guardrail:

- Is a runtime-checkable `Guardrail` instance
- Has a non-empty `name`
- Returns a `Verdict` from `scan()`
- Correctly blocks and allows representative inputs

## Register in `aegis.yaml`

```yaml
providers:
  main:
    type: anthropic
    api_key: secret://env/ANTHROPIC_API_KEY

guardrails:
  keyword:
    pack: aegis_guardrail_my_guard.guard
    mode: block

pipeline:
  ingress: [keyword]

routes:
  default:
    provider: main
```

## Publish your guardrail

Follow the community naming convention: `aegis-guardrail-<name>` on PyPI.
Users install it with `pip install aegis-guardrail-<name>` and declare it in
`aegis.yaml` under `guardrails:`.

## Next steps

- [Govern an MCP tool](govern-mcp-tool.md) — add tool-call governance
- [Streaming modes](../how-to/streaming-modes.md) — implement incremental scanning
