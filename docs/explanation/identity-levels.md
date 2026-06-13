# Identity levels: principal-aware, not multi-tenant

Aegis v2 targets **L2** on this ladder:

- **L0 — anonymous.** `aegis dev` on localhost: no auth, single user.
- **L1 — authenticated.** Virtual API keys (`aeg-...`, SHA-256 hashed, shown
  once at creation) resolve to a `Principal{id, team, labels}` attached to
  every run. Clients hold Aegis keys, never real provider credentials — that
  is much of the point of a gateway.
- **L2 — policy-per-principal.** Existing policy packs read
  `state.principal`: budgets per team, allowed routes per key, residency
  constraints per label, approval authority for paused runs. No new machinery
  — packs simply consume the principal.
- **L3 — multi-tenant. Explicitly out of scope.**

## Why L3 is a different product

Full tenancy is not a column; it is a phase change. Identity inverts (tenants
self-manage users and bring their own IdPs). Configuration stops being a file
and becomes versioned per-tenant data behind an API, with platform-level
policy floors merged over tenant policy. Every table, cache, checkpoint, and
RAG collection gains a partition key with provable isolation. Fairness,
quotas, and billing-grade metering appear. The test matrix roughly doubles.
That work is comparable to the rest of the framework combined.

## The seams are deliberate

Deferring L3 is not designing it out. `Principal.labels` is where a tenant id
would live; RAG namespaces already partition collections; policy is already
evaluated per principal; routes already compile independently. If L3 arrives,
it arrives as addition, not rewrite.

Two defaults follow from taking identity seriously: `aegis serve` refuses to
start without an authenticator unless `--no-auth` is explicit, and `aegis dev`
binds localhost with auth off. Secure by default; frictionless where it is
safe to be.
