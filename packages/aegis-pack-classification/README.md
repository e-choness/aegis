# aegis-gateway-pack-classification

Labels each Aegis request (`pii`, `financial`, `secret`, `medical`, `legal`,
`public`) in `state.labels["classification"]` so later guards can act on it.

```yaml
guardrails:
  classify:
    pack: aegis.classification
pipeline:
  ingress: [classify]
```

See [Classification](https://e-choness.github.io/aegis/packs/classification).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://e-choness.github.io/aegis/changelog) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. Licensed under [AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
