# Policy packs

A **pack** turns one `guardrails:` entry in `aegis.yaml` into pipeline nodes.
First-party packs use exactly the same entry-point contract as third-party
ones — an import-linter rule in CI stops them from reaching into Aegis
internals — so anything they do, your plugin can do too.

All five ship with `pip install aegis-gateway`.

| Pack | `pack:` | Adds | Kind | Options |
|---|---|---|---|---|
| [PII masking](./pii) | `aegis.pii` | ingress mask + egress unmask, or ingress detect | node / guard | `mode: mask \| detect` |
| [Residency](./residency) | `aegis.residency` | ingress guard | guard | `region`, `jurisdiction`, `allowed_regions`, `require_approval` |
| [Classification](./classification) | `aegis.classification` | ingress node | node | — |
| [Budgets](./budgets) | `aegis.budgets` | ingress guard + egress recorder | guard / node | `default_cap` |
| [LLM Guard](./llm-guard) | `aegis.llm_guard` | ingress guard | guard | `scanners`, `threshold` |

## How a pack plugs in

```yaml
guardrails:
  pii:                 # your name for this instance — referenced below
    pack: aegis.pii    # which pack builds it (an aegis.packs entry point)
    mode: mask         # anything else is passed to the pack's factory

pipeline:
  ingress: [pii]       # the pack decides which node goes in which stage;
  egress: [pii]        # listing the name in a stage places that stage's nodes
```

At startup `build_executor()` looks up each `pack:` in the `aegis.packs`
entry-point group and calls its `from_config(name, cfg)` factory, which
returns `{"ingress": [...], "egress": [...]}`. Each route then collects, in
the order you listed them, the nodes each named guardrail contributes to
each stage.

Run `aegis plugin list --group aegis.packs` to see what's installed, and
`aegis policy lint` to catch a `pack:` that isn't.

## Combining packs

Packs never import each other; they cooperate through `RunState`. The
classification pack writes `labels["classification"]`, which any later node
can read. Order matters — list the producer before the consumer:

```yaml
guardrails:
  classify:
    pack: aegis.classification
  pii:
    pack: aegis.pii
    mode: mask
  budget:
    pack: aegis.budgets
    default_cap: 50.0

pipeline:
  ingress: [budget, classify, pii]
  egress: [pii, budget]
```

Want a pack that doesn't exist? [Write one](/develop/plugins) — it is a
normal Python package.
