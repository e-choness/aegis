# Tutorial: Five-minute gateway

In five minutes you will have a local Aegis gateway running, make a governed
chat request through it, and inspect the audit log.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## 1. Install

```bash
pip install aegis-ai
```

## 2. Initialise

```bash
aegis init          # writes aegis.yaml in the current directory
```

The generated `aegis.yaml` enables PII masking and leaves everything else as
commented examples. For this tutorial, replace its contents with the minimal
working config below:

```yaml
providers:
  demo:
    type: openai_compatible
    base_url: http://localhost:8000/v1
    api_key: demo

routes:
  default:
    provider: demo
```

## 3. Start the dev server

```bash
aegis dev           # binds localhost:8000, no auth, FakeProvider
```

The `dev` command always uses `FakeProvider` — a safe in-memory provider that
returns a canned response without making any real model calls. Leave this
terminal running.

## 4. Send a governed chat request

In a second terminal:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"default","messages":[{"role":"user","content":"Hello!"}]}' \
  | python3 -m json.tool
```

You will see an OpenAI-compatible response. Every request passes through the
Aegis pipeline — ingress guards, route resolution, execution, egress guards —
even with FakeProvider.

## 5. Check the audit log

```bash
curl -s http://localhost:8000/v1/audit | python3 -m json.tool
```

The `runs` array contains one entry for every request, with status, principal,
route, and verdict events.

## Next steps

- [Write your first guardrail](first-guardrail.md) — add a custom policy
- [HITL approvals](../how-to/hitl-approvals.md) — pause requests for human review
- [Deployment guide](../how-to/deployment.md) — production setup
