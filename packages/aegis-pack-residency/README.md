# aegis-gateway-pack-residency

Fail-closed data-residency enforcement for Aegis: requests are blocked — or
paused for approval — when a route's endpoint region isn't in the allow-list.

```yaml
guardrails:
  residency_ca:
    pack: aegis.residency
    region: us-east-1
    jurisdiction: US
    allowed_regions: [ca-central-1]
    require_approval: true
pipeline:
  ingress: [residency_ca]
```

See [Residency](https://e-choness.github.io/aegis/packs/residency).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
