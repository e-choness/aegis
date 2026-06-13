# How-to: Budgets

The budgets pack enforces monthly token-cost caps per principal (user or team).
Requests from a principal that has exceeded its cap are blocked before reaching
the provider.

## Configure

```yaml
providers:
  main:
    type: anthropic
    api_key: secret://env/ANTHROPIC_API_KEY

guardrails:
  budgets:
    pack: aegis.budgets

pipeline:
  ingress: [budgets]

routes:
  default:
    provider: main
```

## Setting caps

Caps are set programmatically via the `BudgetLedger`:

```python
from aegis_pack_budgets import BudgetLedger

ledger = BudgetLedger()
ledger.set_cap(principal_id="team-alpha", monthly_usd=50.0)
```

Or via the CLI (when the server is running):

```bash
aegis budget set team-alpha 50.0
```

## How it works

1. **Pre-flight check** — `BudgetGuard.scan()` calls `ledger.is_exceeded(principal)` before any provider call. Exceeded = block.
2. **Post-run recording** — after the run completes, `BudgetGuard.record(state)` posts the actual usage to the ledger.
3. **Monthly reset** — the ledger resets all counters at the start of each calendar month.

## Audit

Blocked budget requests appear in the audit log with `status="blocked"` and a
reason including the principal ID and cap value.

## Tip: per-team budgets

Use `Principal.team` to group users. Set caps on team IDs rather than
individual user IDs to apply team-level spending limits.
