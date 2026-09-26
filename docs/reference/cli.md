# CLI

Every command supports `--help`; `aegis --version` prints the version.

```text
aegis init | serve | chat | explain
aegis config    validate | show
aegis policy    lint | test
aegis plugin    list | info | new | test
aegis provider  add | list | use | test
aegis keys      create | list | revoke
aegis runs      create | list | show | approve | deny
aegis audit     export | verify | inventory
aegis report    summary
aegis rag       index | query
aegis doctor
```

Commands that talk to a running server (`runs`, `explain`, `audit`,
`report`) read **`AEGIS_SERVER_URL`** (default `http://localhost:8767` —
set it to your server, usually `http://localhost:8000`) and
**`AEGIS_API_KEY`**.

## Local setup

### `aegis init`

Write a starter `aegis.yaml`: a `fake` provider, PII masking on, other packs
as commented examples.

```bash
aegis init [--output aegis.yaml] [--force]
```

### `aegis serve`

Load the config, build every route's pipeline, and serve HTTP.

```bash
aegis serve [--config aegis.yaml] [--host 0.0.0.0] [--port 8000] [--no-auth]
            [--keys-file ~/.aegis/keys.json] [--ledger-db aegis_ledger.db]
            [--runs-db aegis_runs.db] [--checkpoint-db aegis_checkpoints.db] [--demo]
```

`--demo` rate-limits pipeline runs per visitor for public demos — see
[Public demos](/guide/deployment#public-demos).

Refuses to start without API-key auth unless `--no-auth` is given.

### `aegis chat`

Send one message through an **in-process** pipeline — no server, no config.
A quick smoke test of the installation.

```bash
aegis chat "Hello" [--route default] [--json]
```

### `aegis doctor`

```bash
aegis doctor [--config aegis.yaml] [--store PATH] [--check-providers]
```

Checks the config parses, the `[pii]` and `[rag]` extras are importable,
the provider profile store is readable, and (opt-in) that saved providers
respond.

## Configuration & policy

```bash
aegis config validate [aegis.yaml]   # schema validation
aegis config show [aegis.yaml]       # resolved config, secrets redacted
aegis policy lint [aegis.yaml]       # AEG-POL-001..006: bad refs, missing packs, streaming downgrades,
                                     #   unenforceable stages, residency mismatches, missing exporters
aegis policy test <fixtures-dir>     # run YAML policy fixtures — see Testing
```

## Plugins

```bash
aegis plugin list [--group aegis.guardrails]
aegis plugin info <name> [--group G]
aegis plugin new <name> --kind guardrail|node|provider|exporter [--output-dir .tmp]
aegis plugin test <path-to-package>  # package tests + independent conformance check
```

See [Write a plugin](/develop/plugins).

## Provider profiles

Saved, named provider profiles for CLI use, stored in `~/.aegis/providers.json`.
Pass keys as `secret://` URIs so the file never holds a credential:

```bash
aegis provider add --name work-openai --type openai_compatible \
  --model gpt-4o-mini --base-url https://api.openai.com/v1 \
  --api-key "secret://env/OPENAI_API_KEY#value" [--region us]
aegis provider list
aegis provider use work-openai
aegis provider test work-openai
```

## Keys

```bash
aegis keys create <principal-id> [--team TEAM] [--keys-file PATH]   # prints aeg-… once
aegis keys list [--keys-file PATH]
aegis keys revoke <key-id> [--keys-file PATH]
```

## Runs & approvals

```bash
aegis runs create "<message>" [--route R] [--approver ID ...] [--background]
aegis runs list [--pending]
aegis runs show <run-id>
aegis runs approve <run-id>
aegis runs deny <run-id>
aegis explain <run-id> | --last [--json]
```

`approve`/`deny` print `AEG-AUTH-003` if your key isn't on the run's
approver list.

## Audit

```bash
aegis audit export [--output FILE] [--format jsonl|csv] [--since-seq N] [--route R]
aegis audit verify FILE              # offline hash-chain check; exit 1 on tamper
aegis audit inventory [--route R] [--json]
aegis report summary [--json]        # inventory, run stats, chain length
```

## RAG

```bash
aegis rag index <dir> [--namespace N] [--glob "**/*.txt"] [--chunk-size 1000] [--chunk-overlap N]
aegis rag query "<text>" [--namespace N] [-k 4] [--json]
```

Uses a local Chroma store in `~/.aegis/rag` with development embeddings —
see [RAG](/guide/rag).
