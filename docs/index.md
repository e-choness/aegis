---
layout: home

hero:
  name: AEGIS
  text: The self-hosted AI gateway that shows its work
  tagline: Put guardrails, human approvals and a tamper-evident audit trail between your apps and any LLM — behind an OpenAI-compatible endpoint, configured in one YAML file.
  image:
    src: /logo.svg
    alt: Aegis shield
  actions:
    - theme: brand
      text: Quickstart →
      link: /guide/quickstart
    - theme: alt
      text: How it works
      link: /guide/concepts
    - theme: alt
      text: Write a plugin
      link: /develop/plugins

features:
  - icon: 🔌
    title: Drop-in OpenAI endpoint
    details: Point any OpenAI SDK at /v1/chat/completions. The model field picks an Aegis route; streaming uses standard SSE frames.
    link: /reference/rest-api
    linkText: REST API
  - icon: 🛡️
    title: Four verdicts, nothing else
    details: Every guardrail returns allow, sanitize, block or require_approval. Every verdict — including allow — is recorded.
    link: /guide/concepts
    linkText: Pipeline & verdicts
  - icon: ⏸️
    title: Pause for a human
    details: require_approval checkpoints the run. A named reviewer approves or denies from the CLI, the API or the /approvals page.
    link: /guide/approvals
    linkText: Human approvals
  - icon: 🔗
    title: Tamper-evident ledger
    details: Runs and route inventory land in a hash-chained SQLite ledger. Export it and verify the chain offline with aegis audit verify.
    link: /guide/audit
    linkText: Audit & evidence
  - icon: 🧩
    title: Plugin-first, no special cases
    details: PII, residency, classification and budgets are packs built on the same entry-point contracts your own plugins use.
    link: /packs/
    linkText: Policy packs
  - icon: 🧪
    title: Scaffold, test, ship
    details: aegis plugin new generates a publishable package with contract tests; aegis plugin test verifies it independently.
    link: /develop/plugins
    linkText: Plugin guide
---

<div class="home-section">

## See it work

A loan-underwriting request carrying a Canadian SIN is routed to a US-region model. The residency guardrail pauses it for a named reviewer, who denies it. `aegis explain` shows why, and the exported ledger verifies offline.

<img class="terminal-demo" src="../images/terminal-demo.svg" alt="Terminal replay: aegis runs create pauses for approval, aegis runs deny, aegis explain shows the verdict trail, aegis audit verify confirms the chain is intact">

Run it yourself with [`examples/scenarios/02_approval_flow.py`](https://github.com/e-choness/aegis/blob/main/examples/scenarios/02_approval_flow.py).

## Sixty seconds to a governed endpoint

::: code-group

```bash [Install & run]
pip install aegis-gateway
aegis init                                 # writes aegis.yaml: fake provider + PII masking
aegis serve --config aegis.yaml --no-auth  # http://localhost:8000
```

```python [Call it (OpenAI SDK)]
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dev")
reply = client.chat.completions.create(
    model="default",  # an Aegis route name
    messages=[{"role": "user", "content": "Email jane@example.com the summary"}],
)
print(reply.choices[0].message.content)
```

```bash [Call it (curl)]
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"default","messages":[{"role":"user","content":"Hello"}]}'
```

:::

</div>
