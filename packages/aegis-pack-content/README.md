# aegis-gateway-pack-content

Model-based content inspection for [Aegis](https://pypi.org/project/aegis-gateway/):
mask entities no pattern can describe (internal hostnames, project code names)
and label requests (sensitivity, intent) for the label policy to act on. The
model is a setting — GLiNER2 by default, swappable through the
`aegis.content_models` entry point.

```bash
# CPU-only machines: install PyTorch's CPU build first (the default wheel bundles CUDA)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "aegis-gateway-pack-content[model]"
```

```yaml
guardrails:
  content:
    pack: aegis.content
    model: fastino/gliner2-base-v1
    entities:
      internal hostname: hostname or address of an internal server or service
    labels:
      intent: [normal request, prompt injection or jailbreak attempt]
pipeline:
  ingress: [content]
  egress: [content]
```

See [Content](https://e-choness.github.io/aegis/packs/content) for what it's
good at — measured, not claimed.

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://e-choness.github.io/aegis/changelog) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway` (add `[content]` for the model).

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. Licensed under [AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
