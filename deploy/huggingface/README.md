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
and the hash-chained audit ledger are real — and every tab shows the
`aegis.yaml` that produces it.

| Tab | What it shows |
|---|---|
| **Privacy** | PII, addresses and internal hostnames masked before the model sees them, restored in the reply |
| **Content policy** | Labels → verdicts: credentials blocked, payment data waits for a reviewer |
| **Prompt attacks** | A local model flags suspected injections for review — with its measured accuracy, false alarms included |
| **Residency + approval** | Personal data headed to a US endpoint pauses for sign-off; clean questions go through |
| **Agent tools** | A compromised mock model tries to email data out; the tool policy holds it for a reviewer |
| **Budgets** | A per-visitor spend cap that blocks the sixth run |
| **Audit** | Explain any run, verify the hash chain, download the evidence |

Also: **`/docs`** (interactive API reference) and **`/v1/chat/completions`**
(OpenAI-compatible; `model` = route name, e.g. `privacy`).

The first minute after the Space wakes up is spent loading the content model
(the header shows "loading models…"); requests work meanwhile, just slower.
Requests are rate-limited per visitor, and data resets whenever the Space
restarts.

This Space is deployed automatically from `deploy/huggingface/` in the Aegis
repository on every release. [Documentation](https://e-choness.github.io/aegis/)
· `pip install aegis-gateway`
