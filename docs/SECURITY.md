# Security Policy

Aegis is an AI gateway: it holds provider credentials, enforces guardrails,
and makes governance claims. We treat reports against those claims as
seriously as memory-safety bugs are treated elsewhere.

## Reporting a vulnerability

Please report privately via **GitHub Security Advisories** ("Report a
vulnerability" on the repository's Security tab). Do not open public issues
for suspected vulnerabilities. You can expect acknowledgment within 72 hours
and a status update within 14 days. Coordinated disclosure is appreciated;
we will credit reporters unless anonymity is requested.

## Scope — what counts

Reports are especially welcome for:

- **Guardrail bypass**: input that reaches a provider, or output that reaches
  a client, despite a policy that should have blocked or sanitized it
  (including via streaming paths, tool calls, tool results, or RAG content).
- **Mask leakage**: PII-mask placeholders or original values appearing in
  model-visible messages, logs, traces, or error output.
- **Authentication/authorization flaws**: virtual-key bypass, approval of
  paused runs without `approvers:` authority, principal spoofing.
- **Secret exposure**: resolved secrets in logs, `repr`, config output,
  checkpoints, or telemetry.
- **Fail-open behavior**: any path where an unknown region, missing guard, or
  failed policy evaluation results in the request proceeding.
- Prompt-injection paths that defeat the tool-result guard chain.

Out of scope: vulnerabilities in upstream model providers, issues requiring a
deliberately weakened configuration (`--no-auth` on a public interface), and
findings in third-party plugins (report to their maintainers; we will help
coordinate).

## Supported versions

| Version | Supported |
|---|---|
| 2.x (latest minor) | yes |
| 2.x (older minors) | critical fixes only |

## Hardening guidance

See the deployment how-to and the explanation docs — in particular the
[residency model](explanation/residency-model.md) (what is enforced vs
declared, and why network egress controls are the last line) and
[identity levels](explanation/identity-levels.md) (secure defaults).
