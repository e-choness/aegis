![aegis-banner](images/banner-wide.jpg)

[![CI](https://github.com/e-choness/aegis/actions/workflows/ci.yml/badge.svg?style=flat-square)](https://github.com/e-choness/aegis/actions/workflows/ci.yml)
[![Docs](https://github.com/e-choness/aegis/actions/workflows/docs.yml/badge.svg?style=flat-square)](https://github.com/e-choness/aegis/actions/workflows/docs.yml)
[![PyPI version](https://img.shields.io/pypi/v/aegis-gateway?style=flat-square)](https://pypi.org/project/aegis-gateway/)
[![Python versions](https://img.shields.io/pypi/pyversions/aegis-gateway?style=flat-square)](https://pypi.org/project/aegis-gateway/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![Code style: ruff + pyright](https://img.shields.io/badge/code%20style-ruff%20%2B%20pyright-black?style=flat-square)](https://github.com/astral-sh/ruff)

Aegis is a self-hosted AI gateway that shows you exactly why a request was
blocked, masked, or paused, and keeps a tamper-evident record of every one of
those decisions — no enterprise tier required.

## See it work

A loan-underwriting request carrying a Canadian SIN gets routed to a
US-region model. The residency guardrail doesn't block that outright — it
pauses for a named human reviewer. She denies it. The full trail, including
her name, is in the evidence ledger and verifies offline.

> **Cast pending recording.** The walkthrough below runs correctly today,
> unattended, against a live `aegis serve` process — recording it as an
> asciinema cast is the one step still left to a human. Run it yourself:
> `docker compose run --rm dev uv run python examples/scenarios/02_approval_flow.py`
> (see that file's docstring for the two-command setup).

## Install

```bash
pip install aegis-gateway
aegis init                                 # writes aegis.yaml — PII masking on, fake provider
aegis serve --config aegis.yaml --no-auth  # binds :8000, zero credentials needed
```

Point any OpenAI client at it:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dev")
response = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## The config that produces the scenario above

`examples/fintech.yaml` — one route, two guardrails, zero code:

```yaml
providers:
  us_underwriting_llm:
    type: fake
    complete_response: "[underwriting] synthetic risk assessment — not a real model"
    residency:
      region: us-east-1

guardrails:
  pii:
    pack: aegis.pii
    mode: mask
  residency_ca:
    pack: aegis.residency
    region: us-east-1
    jurisdiction: US
    allowed_regions: [ca-central-1]
    require_approval: true   # pause for a human, don't auto-deny

pipeline:
  ingress: [pii, residency_ca]
  egress: [pii]

routes:
  underwriting:
    provider: us_underwriting_llm
    risk_rating: high
    review_interval_days: 180
    owner: risk-team@example.com
```

Guardrail packs are plugins — `aegis.pii` and `aegis.residency` are built on
the same public contract a third-party pack uses (`aegis plugin new --kind
guardrail`, see the [write-a-pack guide](https://e-choness.github.io/aegis/how-to/write-a-pack/)).
There is no separate "built-in" code path.

## `aegis explain` on the denied run

```text
run 13cdfd49  route=underwriting  principal=svc-underwriting  status=denied  config=sha256:8b01931ef…
────────────────────────────────────────────────────────────────────────
  guard         residency_ca              REQUIRE_APPROVAL  reason=residency: region 'us-east-1' for route 'underwriting' is not in the allowed set ['ca-central-1']
  ingress       residency_ca              DENIED  reason=run denied by reviewer
────────────────────────────────────────────────────────────────────────
  short-circuited at ingress/residency_ca · provider never called
```

The evidence ledger's record of that denial names the reviewer:
`{"principal_id": "jane", "decision": "denied", "at": "2026-09-20T03:07:27Z"}`
— and `aegis audit export --route underwriting | aegis audit verify` proves
the whole hash-chained history hasn't been tampered with, offline, without
trusting the server that produced it.

## Four verdicts, nothing else

Every guardrail returns exactly one of:

- **allow** — continue unchanged.
- **sanitize** — continue with mutated content (masked PII, redacted text).
- **block** — terminal; the client gets a refusal, the ledger gets the reason.
- **require_approval** — the run pauses via a checkpointed interrupt; a named
  human resumes it with approve or deny. Approval authority is itself
  policy — an `approvers:` list is checked against the resuming principal.

Every verdict, including `allow`, is an audit event. "Which guard let this
through, and who signed off on the one that didn't?" is always answerable.

## Why this exists

Structured audit logging of model-provider decisions is an enterprise or
paid-tier feature on most gateways in this space. Here it's the default,
open-source behaviour — every guardrail verdict is a hash-chained ledger
entry from the moment the server starts, not an add-on you upgrade into once
a compliance team asks for evidence.

## Features

- **Guardrail pipeline** — ingress, tool-call, tool-result, and egress
  stages; verdicts `allow / block / sanitize / require_approval`
- **Provider-agnostic** — OpenAI, Anthropic, Bedrock, Vertex, or any
  OpenAI-compatible endpoint; hot-swappable per route
- **Human-in-the-loop** — `require_approval` pauses execution via LangGraph
  `interrupt()`; resume via REST or `aegis runs approve|deny`
- **Evidence ledger** — hash-chained, append-only audit trail shaped for
  regulatory model-inventory reporting; `aegis audit export`/`verify`
- **Streaming** — true incremental streaming when all egress guards support
  `scan_chunk()`; buffered SSE otherwise; `policy lint` reports downgrades
- **Tool governance** — argument scan + masked-data exfiltration check on
  every tool call; prompt-injection scan on every tool result
- **Residency / data sovereignty** — declared region metadata, fail-closed or
  pause-for-approval provider filtering, per-request audit
- **Plugin-first** — five entry-point contracts (`ModelProvider`,
  `Guardrail`, `PipelineNode`, `SecretProvider`, `Exporter`, plus
  `Authenticator` shipped by `aegis-server`); `aegis plugin new` scaffolds a
  publishable package for any of them

See [Architecture](https://e-choness.github.io/aegis/explanation/architecture/)
and [the pipeline & verdict model](https://e-choness.github.io/aegis/explanation/pipeline-and-verdicts/)
for how the kernel, the graph, and the policy packs fit together.

## Documentation

- [Full docs](https://e-choness.github.io/aegis/) — tutorials, how-to guides, reference, architecture
- [Write a pack](https://e-choness.github.io/aegis/how-to/write-a-pack/) — build and publish a guardrail, node, provider, or exporter
- [Contributing](docs/CONTRIBUTING.md) · [Security policy](docs/SECURITY.md) · [License](LICENSE)
