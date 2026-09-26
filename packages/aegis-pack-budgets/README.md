# aegis-gateway-pack-budgets

Per-principal monthly spend caps for Aegis: an ingress guard blocks
principals over their cap, and an egress recorder charges each run.

```yaml
guardrails:
  budget:
    pack: aegis.budgets
    default_cap: 100.0
pipeline:
  ingress: [budget]
  egress: [budget]
```

See [Budgets](https://e-choness.github.io/aegis/packs/budgets).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
