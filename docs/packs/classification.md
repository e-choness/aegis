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

Rules are checked most severe first; the first match wins, so a message with
an email address *and* a password is labelled `secret`.

| Label | Matches |
|---|---|
| `secret` | credentials — see below |
| `financial` | 16-digit card-number patterns |
| `pii` | email addresses, US-style phone numbers |
| `medical` | *diagnosis*, *prescription*, *patient*, *HIPAA* |
| `legal` | *attorney-client*, *privileged*, *confidential* |
| `public` | anything else |

### What counts as a secret

A message is labelled `secret` when it contains a credential, not when it
merely talks about one:

| Shape | Example |
|---|---|
| Private keys | `-----BEGIN RSA PRIVATE KEY-----` |
| Provider keys | AWS `AKIA…`, Google `AIza…`, GitHub `ghp_…`, Slack `xoxb-…`, Stripe `sk_live_…` |
| Tokens | JWTs (`eyJ….eyJ….…`), `Authorization: Bearer …` |
| Connection strings | `postgres://user:password@host` |
| Key/value pairs | `api_key: …`, `DB_PASSWORD=…`, `"client_secret": "…"` — the value must be 6+ characters with a digit or symbol |
| Phrases | "the password is Tr0ub4dor&3", "the login is ops / Hunter2-Prod" |

"Rotate your password every 90 days", `password: required`, `"token": null`
and GitHub Actions `secrets.NPM_TOKEN` references are not secrets. These rules are measured
against the labelled prompts in `evals/` on every CI run (see
[Contributing](/CONTRIBUTING#guard-evals)).

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
