# Budgets

`aegis.budgets` caps monthly model spend per principal. Before the provider
is called, it blocks any principal whose spend this calendar month has
reached their cap.

```yaml
guardrails:
  budget:
    pack: aegis.budgets
    default_cap: 100.0      # USD per principal per month (default 100.0)

pipeline:
  ingress: [budget]         # list it first: a blocked request should cost nothing
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

::: warning Current state
The pre-flight check is wired into `aegis serve`, but spend isn't recorded
automatically yet — nothing calls `BudgetGuard.record(state)` after a run,
and the ledger is in memory. Until that lands, call `record()` yourself when
embedding the pipeline, or treat the pack as a hard stop you can trip
manually.
:::
