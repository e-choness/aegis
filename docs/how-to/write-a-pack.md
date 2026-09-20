# How-to: Write a pack

A "pack" is a publishable Python package that adds a guardrail, a pipeline
node, a provider, or an evidence exporter to Aegis. Discovery is entirely
`importlib.metadata` entry points — there is no registry to submit to and no
core code to patch. `pip install` your pack, list it in `aegis.yaml` (for
guardrails/nodes), and it runs.

## Entry-point groups

| Group | What it registers | Constructed by |
|---|---|---|
| `aegis.guardrails` | A `Guardrail` (`scan(state) -> Verdict`) | Wrapped by a `GuardNode` |
| `aegis.nodes` | A raw `PipelineNode` (`run(state) -> RunStateDelta`) | Used directly in a pipeline stage |
| `aegis.providers` | A `ModelProvider` (`complete`/`stream`/`embed`/`info`) | `build_provider()` from `type:` in YAML |
| `aegis.exporters` | An `Exporter` (`export(records) -> None`) | Ledger export destinations |
| `aegis.packs` | A `from_config(name, cfg) -> dict[str, list[PipelineNode]]` factory | `build_executor()` when a route declares the guardrail in YAML |

Guardrails and nodes are the two kinds a route can actually reference from
`aegis.yaml`'s `guardrails:` section — that reference resolves through the
`aegis.packs` factory convention, which is why scaffolding those two kinds
also generates a `factory.py`.

## Scaffold one

```bash
aegis plugin new my-guard --kind guardrail   # or: node | provider | exporter
```

This generates a package under `.tmp/aegis-guardrail-my-guard/` (`--output-dir`
to change it) with:

- `pyproject.toml` — correct entry-point groups already filled in
- `src/aegis_guardrail_my_guard/guard.py` — a stub `MyGuard` that always allows
- `src/aegis_guardrail_my_guard/factory.py` — `from_config` wiring it into `ingress` (guardrail/node kinds only)
- `conftest.py` — puts `src/` on `sys.path` and sanity-imports `aegis_core.testing`
- `tests/test_contract.py` — a contract-kit test that passes with zero edits
- `tests/test_factory.py` — a `from_config` round-trip test (guardrail/node kinds only)

## Verify it

```bash
aegis plugin test .tmp/aegis-guardrail-my-guard
```

This runs the package's own `pytest` suite, then an independent conformance
check the CLI runs itself — regardless of what you did to your own test file.
It verifies your class still satisfies its Protocol (this is what catches a
guardrail missing its `streaming: ClassVar` attribute) and, for
guardrail/node kinds, that `from_config` returns real `PipelineNode`
instances and doesn't leak `mask_map`/`messages` into event data.

## Implement it

Replace the stub body in `guard.py` (or `node.py` / `provider.py` /
`exporter.py`). For a guardrail:

```python
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class MyGuard:
    name = "my_guard"
    streaming = "none"  # or "incremental" if you implement IncrementalGuardrail

    async def scan(self, state: RunState) -> Verdict:
        if is_bad(state.messages[-1].content):  # noqa: F821 — your detection logic
            return Verdict.block(reason="policy violation")
        return Verdict.allow()
```

`streaming` is not decorative — routes composed entirely of `"incremental"`
egress guards can true-stream to the client; a single `"none"` guard forces
the whole response to buffer first.

## Publish it

```toml
[project]
name = "aegis-guard-my-guard"
dependencies = ["aegis-gateway-core>=2.0.0a0"]

[project.entry-points."aegis.guardrails"]
my_guard = "aegis_guard_my_guard:MyGuard"

[project.entry-points."aegis.packs"]
"aegis.my_guard" = "aegis_guard_my_guard.factory:from_config"
```

`pip install aegis-guard-my-guard` (or `pip install -e .` during development),
then reference it by pack name in `aegis.yaml`:

```yaml
guardrails:
  my_guard:
    pack: aegis.my_guard
pipeline:
  ingress: [my_guard]
```

No core code changes, no PR against this repository — that is the whole
point of the entry-point boundary.

## Worked example

`packages/aegis-pack-pii` is the real thing: one guardrail (`PiiMaskGuard`),
two nodes (`PiiMaskNode`, `PiiUnmaskNode`), and a `factory.py` whose
`from_config` contributes to both `ingress` and `egress` depending on
`mode: mask` vs `mode: detect`. Read `factory.py` there once your pack needs
more than the scaffold's one-node stub.
