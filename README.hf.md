---
title: Aegis Pipeline Showcase
emoji: 🛡️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
# No HF_TOKEN or secrets — the demo runs entirely on the built-in mock provider.
---

# Aegis v2 — Pipeline Showcase

This Space hosts the Aegis governance showcase. No API keys are required:
the server runs on the **FakeProvider** (mock) and demonstrates ingress/egress
guardrails, PII mask/unmask, and HITL approvals.

- **Showcase page:** `/showcase`
- **OpenAPI docs:** `/docs`
- **OpenAI-compat API:** `/v1/chat/completions`

Built from the [e-choness/aegis](https://github.com/e-choness/aegis) repo.
