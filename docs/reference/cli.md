# CLI reference

Aegis ships a `typer`-based CLI. All commands support `--help`.

```
aegis init | dev | serve [--no-auth]
aegis chat | run            (--route --stream --json)
aegis provider add|list|use|test
aegis policy  lint|show|test
aegis plugin  list|info|scaffold
aegis runs    list [--pending]|show|approve|deny|resume
aegis keys    create|list|revoke
aegis rag     index|query
aegis doctor  [--config] [--store] [--check-providers]
```

## `aegis init`

Write a starter `aegis.yaml` with PII enabled and other sections present but commented.

```bash
aegis init [--output aegis.yaml] [--force]
```

## `aegis dev`

Start a local development server. Uses `FakeProvider` (no real model calls),
no authentication required, binds `localhost`.

```bash
aegis dev [--host 127.0.0.1] [--port 8000]
```

## `aegis serve`

Start the production server. Refuses to start without an authenticator unless
`--no-auth` is passed explicitly.

```bash
aegis serve [--host 0.0.0.0] [--port 8000] [--no-auth]
```

## `aegis chat`

Send a governed chat message and print the response.

```bash
aegis chat "Hello, world!" [--route default] [--stream] [--json]
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

Lint and test governance policies.

```bash
aegis policy lint              # check aegis.yaml for policy errors
aegis policy test examples/fixtures/   # run fixture-based policy tests
```

## `aegis plugin`

Discover and scaffold plugins.

```bash
aegis plugin list              # list installed plugins
aegis plugin info my-guardrail
aegis plugin scaffold guardrail my-guard [--output-dir .]
aegis plugin scaffold provider my-provider
```

## `aegis runs`

Manage run records (requires a running server).

```bash
aegis runs list [--pending]
aegis runs show <run-id>
aegis runs approve <run-id>
aegis runs deny <run-id>
```

## `aegis keys`

Manage virtual API keys.

```bash
aegis keys create [--name friendly-name]
# Prints the key once: aeg-<64-hex-chars> (not stored; SHA-256 hash only)
aegis keys list
aegis keys revoke <key-id>
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
aegis doctor               # run all checks
aegis doctor --config      # check aegis.yaml only
aegis doctor --store       # check provider store
aegis doctor --check-providers   # test provider reachability
```
