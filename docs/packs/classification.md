# Classification

`aegis.classification` labels each request so later nodes can make decisions
without re-scanning the text. It runs a small, ordered set of regex rules
over the **latest user message** and writes the first match to
`state.labels["classification"]`.

```yaml
guardrails:
  classify:
    pack: aegis.classification

pipeline:
  ingress: [classify]
```

## Labels

Rules are checked in this order; the first match wins.

| Label | Matches |
|---|---|
| `pii` | email addresses, US-style phone numbers |
| `financial` | 16-digit card-number patterns |
| `secret` | `api_key=…`, `password: …`, `token=…` and similar |
| `medical` | *diagnosis*, *prescription*, *patient*, *HIPAA* |
| `legal` | *attorney-client*, *privileged*, *confidential* |
| `public` | anything else |

The node never blocks — it only labels. The label is recorded in the run's
events.

## Acting on the label

Put the classifier first, then a guard that reads the label:

```python
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class NoSecretsGuard:
    name = "no_secrets"
    streaming = "none"

    async def scan(self, state: RunState) -> Verdict:
        if state.labels.get("classification") == "secret":
            return Verdict.block("credentials must not be sent to a model")
        return Verdict.allow()
```

```yaml
pipeline:
  ingress: [classify, no_secrets]
```

The rules are intentionally cheap and conservative; for richer detection,
combine with [PII masking](./pii) or [LLM Guard](./llm-guard), or write a
node with your own classifier.
