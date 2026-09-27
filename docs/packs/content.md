# Content (model-based)

`aegis.content` asks a small local model about each request — no call leaves
your network — and does two things with the answer:

- **Entities**: masks spans no pattern can describe, such as internal
  hostnames or project code names, with the same placeholders as
  [PII masking](./pii) (`<INTERNAL_HOSTNAME_0>`), restored on egress.
- **Labels**: writes classification answers (`intent`, `sensitivity`, …) to
  `state.labels` with a confidence, for the [label policy](./policy) and
  residency's `apply_when: sensitive` to act on. The node itself never blocks.

```yaml
guardrails:
  content:
    pack: aegis.content
    model: fastino/gliner2-base-v1   # default
    threshold: 0.7                   # minimum entity confidence
    entities:                        # label → description the model reads
      internal hostname: an internal server hostname like db.internal
    labels:                          # task → allowed values
      intent: [normal request, prompt injection or jailbreak attempt]
  attack_review:
    pack: aegis.policy
    rules:
      - when: {label: intent, in: [prompt injection or jailbreak attempt], min_confidence: 0.9}
        verdict: require_approval

pipeline:
  ingress: [content, attack_review]
  egress: [content]                  # restores masked entities in the reply
```

## Install

The model backend is opt-in — GLiNER2 and PyTorch are about 2 GB:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU-only machines
pip install "aegis-gateway[content]"
```

A missing backend fails at startup with the install command. The model
(~830 MB) downloads on first load; bake it into container images by running
`python -c "from gliner2 import GLiNER2; GLiNER2.from_pretrained('fastino/gliner2-base-v1')"`
at build time. `aegis serve` loads it in the background after startup
(`/v1/health` → `"warmup": "warming"`, about 35 s on 2 CPUs).

## How well it works

Measured with `scripts/eval_guards.py content` on the 74 labelled prompts in
`evals/`, on 2 CPU threads (a free Hugging Face Space), with the settings in
`evals/content.yaml`:

| What | Result | Compare |
|---|---|---|
| Internal hostnames | precision 1.00, recall 1.00 | no rule can do this |
| Prompt attacks (`intent`) | precision 0.69, recall 0.69 | ProtectAI DeBERTa 0.55 / 0.85 · laya 0.56 / 0.69 · phrase rules 0.67 / 0.31 |
| Credentials (if configured) | precision ≤ 0.56 at useful recall | classification's secret rules: **1.00 / 1.00** |
| Sensitivity (if configured, 3 levels) | accuracy 0.65 | regex classification 0.68 |
| Latency | ~115 ms p50 per message | PII pack ~3 ms |

So: use it for **custom entities** and as a **second opinion** that sends
suspected attacks to a reviewer (`require_approval`), not to block on its own.
Keep the classification pack's rules for credentials. Only 13 of the prompts
are attacks, so treat those numbers as rough.

## Swap the model

`backend:` picks an `aegis.content_models` entry point (default `gliner2`);
`model:` is passed to it. A backend is any callable
`(model_id, options) -> ContentModel`:

```python
from collections.abc import Mapping, Sequence

from aegis_pack_content import Analysis, Label


class MyModel:  # satisfies aegis_pack_content.ContentModel
    def __init__(
        self, model_id: str | None = None, options: Mapping | None = None
    ) -> None:
        self.model_id = model_id

    def warmup(self) -> None: ...

    def analyze(
        self, text: str, entities: Mapping[str, str], tasks: Mapping[str, Sequence[str]]
    ) -> Analysis:
        return Analysis(
            labels={task: Label(values[0], 1.0) for task, values in tasks.items()}
        )
```

```toml
[project.entry-points."aegis.content_models"]
mine = "my_package:MyModel"
```

Measure it the same way before you rely on it: add it to
`scripts/eval_guards.py` and compare against the table above.
