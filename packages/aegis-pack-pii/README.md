# aegis-gateway-pack-pii

PII masking for Aegis, powered by Microsoft Presidio. In `mask` mode the
model never sees personal data: entities become placeholders on the way in
and are restored on the way out.

```yaml
guardrails:
  pii:
    pack: aegis.pii
    mode: mask        # or: detect — block requests containing PII
pipeline:
  ingress: [pii]
  egress: [pii]
```

Needs the spaCy model: `python -m spacy download en_core_web_sm`.
See [PII masking](https://e-choness.github.io/aegis/packs/pii).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
