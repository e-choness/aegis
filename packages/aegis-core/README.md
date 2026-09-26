# aegis-gateway-core

The Aegis kernel: typed `aegis.yaml` configuration, `secret://` resolution,
entry-point plugin discovery, the LangGraph pipeline (ingress → execute →
egress), the four-verdict guardrail contract, and contract test kits for
plugin authors.

```bash
pip install aegis-gateway-core          # add [rag] for Chroma/pgvector retrieval
```

Depend on this package when you **write a plugin**. The public API for pack
factories is `aegis_core.packs`; guardrails implement
`async scan(state) -> Verdict`.

```python
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class NoTicketsGuard:
    name = "no_tickets"
    streaming = "none"

    async def scan(self, state: RunState) -> Verdict:
        if "INC-" in state.messages[-1].content:
            return Verdict.block("internal ticket ids must not leave the company")
        return Verdict.allow()
```

See [Write a plugin]({DOCS}/develop/plugins) and [Testing]({DOCS}/develop/testing).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://e-choness.github.io/aegis/changelog) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. Licensed under [AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
