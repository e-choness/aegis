# CLI reference

Aegis ships a `typer`-based CLI. All commands and subcommands support
`--help`.

```
aegis init | serve [--no-auth] | chat | explain
aegis config    validate|show
aegis provider  add|list|use|test
aegis policy    lint|test
aegis plugin    list|info|new|test
aegis runs      create|list [--pending]|show|approve|deny
aegis audit     export|verify|inventory
aegis report    summary
aegis keys      create|list|revoke
aegis rag       index|query
aegis doctor    [--config] [--store] [--check-providers]
```

## `aegis init`

Write a starter `aegis.yaml` — a `fake` provider (no credentials needed) and
PII masking active, other guardrail packs present as commented examples.

```bash
aegis init [--output aegis.yaml] [--force]
```

## `aegis serve`

Start the server: loads `aegis.yaml`, builds the pipeline from it, and wires
a SQLite-backed checkpointer so `require_approval` guardrails can actually
be resumed later. Refuses to start without an authenticator unless
`--no-auth` is passed explicitly.

```bash
aegis serve --config aegis.yaml [--host 0.0.0.0] [--port 8000] [--no-auth] \
  [--keys-file ~/.aegis/keys.json] [--ledger-db aegis_ledger.db] \
  [--checkpoint-db aegis_checkpoints.db]
```

There is no separate development server command — `type: fake` in
`aegis.yaml` plus `--no-auth` is the zero-credential path (what `aegis init`
writes by default).

## `aegis chat`

Run a message through an in-process pipeline (no server, no config file —
this is a quick local check, not a client of a running `aegis serve`).

```bash
aegis chat "Hello, world!" [--route default] [--json]
```

## `aegis explain`

Render the verdict trail for a run against a live server: one row per
guardrail verdict, coloured by kind, with a note when the provider was
never reached.

```bash
aegis explain <run-id> [--last] [--json]
```

## `aegis config`

```bash
aegis config validate aegis.yaml   # parse + Pydantic validation
aegis config show aegis.yaml       # resolved config, secrets redacted
```

## `aegis provider`

Manage saved provider profiles.

```bash
aegis provider add --name my-provider --type anthropic --api-key sk-...
aegis provider list
aegis provider use my-provider
aegis provider test my-provider
```

## `aegis policy`

Lint and test governance policies without starting a server.

```bash
aegis policy lint aegis.yaml            # broken pipeline refs, uninstalled packs
aegis policy test examples/fixtures/    # run fixture-based policy tests
```

## `aegis plugin`

Discover, scaffold, and verify plugins — see the
[write-a-pack guide](../how-to/write-a-pack.md) for the full workflow.

```bash
aegis plugin list [--group aegis.guardrails]
aegis plugin info my-guardrail
aegis plugin new my-guard --kind guardrail|node|provider|exporter [--output-dir .tmp]
aegis plugin test .tmp/aegis-guardrail-my-guard   # pytest + independent conformance check
```

## `aegis runs`

Manage run records against a live server (`AEGIS_SERVER_URL`,
`AEGIS_API_KEY`).

```bash
aegis runs create "message" [--route default] [--approver jane] [--background]
aegis runs list [--pending]
aegis runs show <run-id>
aegis runs approve <run-id>
aegis runs deny <run-id>
```

## `aegis audit`

Export and verify the evidence ledger.

```bash
aegis audit export [--format jsonl|csv] [--output FILE] [--since-seq N] [--route R]
aegis audit verify FILE          # offline hash-chain check, exits 1 on tamper
aegis audit inventory [--route R] [--json]
```

## `aegis report`

```bash
aegis report summary   # inventory table, run stats, chain length
```

## `aegis keys`

Manage virtual API keys.

```bash
aegis keys create <principal-id> [--team TEAM] [--keys-file ~/.aegis/keys.json]
# Prints the key once: aeg-<64-hex-chars> (not stored; SHA-256 hash only)
aegis keys list [--keys-file ~/.aegis/keys.json]
aegis keys revoke <key-id> [--keys-file ~/.aegis/keys.json]
```

## `aegis rag`

Index documents and query the vector store.

```bash
aegis rag index path/to/docs/
aegis rag query "What is GDPR article 17?"
```

## `aegis doctor`

Diagnose the local environment.

```bash
aegis doctor                     # run all checks
aegis doctor --config aegis.yaml # check a specific config file
aegis doctor --store             # check provider profile store
aegis doctor --check-providers   # test provider reachability
```
