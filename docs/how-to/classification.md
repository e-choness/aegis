# How-to: Content classification

The classification pack labels every request with a content class (pii,
financial, secret, medical, legal, or public) by running regex patterns over
the first user message. Downstream packs read `state.labels["classification"]`
without importing each other.

## Install

```bash
pip install aegis-gateway
```

Classification has no extra dependencies — it ships in the core install.

## Configure

```yaml
providers:
  main:
    type: anthropic
    api_key: secret://env/ANTHROPIC_API_KEY

guardrails:
  classify:
    pack: aegis.classification

pipeline:
  ingress: [classify]

routes:
  default:
    provider: main
```

## Default patterns

| Class | Trigger examples |
|---|---|
| `pii` | email addresses, phone numbers, SSNs |
| `financial` | routing numbers, credit card patterns |
| `secret` | API keys, passwords, tokens |
| `medical` | diagnoses, medications, ICD codes |
| `legal` | contract, NDA, GDPR |
| `public` | catch-all when nothing else matches |

## Reading the label downstream

Any downstream pack (guardrail, node) can read the label from `RunState`:

```python
from aegis_core.pipeline import Verdict


async def scan(self, messages, state):
    classification = state.labels.get("classification", "public")
    if classification == "secret":
        return Verdict.block("Secret content blocked by policy")
    return Verdict.allow()
```

## Combining with residency

The residency pack can filter providers based on the classification label via
`Principal.labels`. See the [residency how-to](residency.md) for details.
