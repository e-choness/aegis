# Tutorial: Five-minute gateway

In five minutes you will have a local Aegis gateway running, make a governed
chat request through it, and inspect the audit log.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## 1. Install

```bash
pip install aegis-gateway
```

## 2. Initialise

```bash
aegis init          # writes aegis.yaml in the current directory
```

The generated `aegis.yaml` already wires a `fake` provider — a safe in-memory
provider that returns a canned response without making any real model calls
— plus PII masking, so it works with zero credentials as-is:

```yaml
providers:
  default:
    type: fake
    complete_response: "[aegis] hello — replace this provider with a real one"

guardrails:
  pii:
    pack: aegis.pii
    mode: mask

pipeline:
  ingress: [pii]
  egress: [pii]

routes:
  default:
    provider: default

auth:
  type: none
```

## 3. Start the server

```bash
aegis serve --config aegis.yaml --no-auth   # binds localhost:8000, no auth
```

Leave this terminal running.

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
