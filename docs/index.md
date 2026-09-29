---
layout: home

# The hero is docs/.vitepress/theme/components/AegisHero.vue.

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

One config, one CLI. A prompt with an API key never reaches a model. A clean question to the loan-underwriting route — whose model runs in a US region — goes straight through; the same route with a Canadian SIN pauses for a named reviewer, who denies it. `aegis explain` shows why, and the exported ledger verifies offline.

<img class="terminal-demo" src="../media/terminal-demo.svg" alt="Terminal replay: aegis plugin list shows the policy packs; a prompt with an API key is blocked; a clean underwriting question is answered; one carrying a SIN pauses for approval and reviewer jane denies it; aegis explain shows the verdict trail; aegis audit verify confirms the chain is intact">

**Try it in your browser:** the [live demo](https://huggingface.co/spaces/echoness/aegis-server) runs the real guardrails against a mock model — paste a prompt with an email address or a SIN, switch to the *underwriting* route, and approve or deny the paused run. Nothing to install.

Or run it yourself from a clone with `docker compose run --rm dev bash scripts/cli-tour.sh` — the config is [`examples/cli-tour.yaml`](https://github.com/e-choness/aegis/blob/main/examples/cli-tour.yaml).

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
