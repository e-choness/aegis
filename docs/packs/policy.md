# Label policy

`aegis.policy` turns labels into verdicts. Labelling nodes — [classification](./classification)
or a model-backed labeler — only *describe* a request; the policy is where you
say what each label means on this route: block it, pause it for a reviewer, or
let it through.

```yaml
guardrails:
  classify:
    pack: aegis.classification
  content_policy:
    pack: aegis.policy
    rules:
      - when: {label: classification, in: [secret]}
        verdict: block
        reason: credentials must not be sent to a model
      - when: {label: classification, in: [pii, financial]}
        verdict: require_approval
        reason: personal data needs sign-off

pipeline:
  ingress: [classify, content_policy]   # label first, then decide
```

Rules are checked in order and the **first match wins**; a request no rule
matches is allowed. Ships in `aegis-gateway-pack-classification`.

## Rules

| Field | Required | Notes |
|---|---|---|
| `when.label` | yes | Key in `state.labels` — `classification` for the classification pack. |
| `when.in` | yes | Label values that match (a list, or one string). |
| `when.min_confidence` | no | 0–1. Applies when the labeler also records `"<label>.confidence"`; labels without a confidence (regex classification) always pass it. |
| `verdict` | yes | `block`, `require_approval` or `allow`. An `allow` rule stops later rules from matching — use it for exceptions. |
| `reason` | no | Shown in the verdict and the evidence ledger. Default: `policy: <label> is '<value>'`. |

A missing or malformed rule fails at startup with `AEG-CFG`, not on the first
request.

## Same labels, different routes

The labels don't change between routes; the policy does. An internal
analytics route might allow `financial` content that a public chatbot route
must block:

```yaml
guardrails:
  classify:
    pack: aegis.classification
  public_policy:
    pack: aegis.policy
    rules:
      - when: {label: classification, in: [secret, financial, pii]}
        verdict: block
  analyst_policy:
    pack: aegis.policy
    rules:
      - when: {label: classification, in: [secret]}
        verdict: block

providers:
  llm:
    type: fake

routes:
  chatbot:
    provider: llm
    pipeline: {ingress: [classify, public_policy]}
  analytics:
    provider: llm
    pipeline: {ingress: [classify, analyst_policy]}
```
