# aegis-gateway-pack-pii

PII masking for Aegis, powered by Microsoft Presidio. In `mask` mode the
model never sees personal data: entities become placeholders on the way in
and are restored on the way out.

```yaml
guardrails:
  pii:
    pack: aegis.pii
    mode: mask        # or: detect — block requests containing PII
    threshold: 0.4    # minimum confidence (default)
    allow_list: [Aegis]
    # entities: [PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CA_SIN]  — or ALL
pipeline:
  ingress: [pii]
  egress: [pii]
```

By default only identifying entities are masked (names, contact details,
account and government IDs — including Canadian SINs); noisy types such as
dates and URLs are opt-in.

Needs the spaCy model: `python -m spacy download en_core_web_sm`.
See [PII masking](https://e-choness.github.io/aegis/packs/pii).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://e-choness.github.io/aegis/changelog) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. Licensed under [AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
