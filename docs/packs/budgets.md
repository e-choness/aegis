# Budgets

`aegis.budgets` caps monthly model spend per principal. The pack adds two
nodes that share one ledger:

- on **ingress**, a guard blocks any principal whose spend this calendar
  month has reached their cap — before the provider is called;
- on **egress**, a recorder charges the finished run's usage
  (`usage.cost`, as reported by the provider) to the principal.

```yaml
guardrails:
  budget:
    pack: aegis.budgets
    default_cap: 100.0      # USD per principal per month (default 100.0)

pipeline:
  ingress: [budget]         # list it first: a blocked request should cost nothing
  egress: [budget]          # without this, spend is never recorded
```

A blocked request's reason names the principal, the amount spent and the
cap, and appears in `aegis explain` and the ledger. Requests without a
principal are allowed.

## Per-principal caps

From Python, `BudgetLedger` takes explicit caps; `None` means unlimited:

```python
from aegis_pack_budgets import BudgetGuard, BudgetLedger

ledger = BudgetLedger(
    caps={"svc-batch": 500.0, "svc-admin": None},
    default_cap=25.0,
)
guard = BudgetGuard(ledger, name="budget")
```

Keys are principal ids, so issue one key per team service
(`aegis keys create svc-batch --team data`) to budget by team.

## Things to know

- The budget ledger lives in memory: spend resets when the server restarts.
- The recorder needs each run's final usage, so routes with budgets buffer
  streamed responses.
- Spend comes from the provider's reported cost; a provider that doesn't
  report cost (e.g. `fake`) is never charged.
