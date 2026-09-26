---
title: Aegis Gateway Demo
emoji: 🛡️
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: Self-hosted AI gateway — guardrails, approvals, audit
---

# Aegis — live demo

A running [Aegis](https://github.com/e-choness/aegis) gateway. No API keys and
no real model: every provider is a mock, but the guardrails, human approvals
and the hash-chained audit ledger are real.

- **`/showcase`** — try prompts against the governed routes
- **`/approvals`** — approve or deny runs paused by the residency guardrail
- **`/docs`** — interactive API reference
- **`/v1/chat/completions`** — OpenAI-compatible endpoint (`model` = route: `default` or `underwriting`)

Try the `underwriting` route with a message containing a SIN (e.g.
`Applicant SIN is 046-454-286`): PII is masked, and the residency guardrail
pauses the run for approval instead of sending Canadian data to a US region.

Requests are rate-limited per visitor, and data resets whenever the Space
restarts.

This Space is deployed automatically from `deploy/huggingface/` in the Aegis
repository on every release. [Documentation](https://e-choness.github.io/aegis/)
· `pip install aegis-gateway`
