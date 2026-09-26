# Error codes

Errors have the form `AEG-<AREA>-<NNN>` and carry a **what**, a **why** and
a **fix**:

```text
[AEG-CFG-003] Route 'default' references unknown provider 'main'. Declared providers: ['primary']
  Why: One or more fields in aegis.yaml failed schema validation.
  Fix: Review the field errors below and correct the configuration.
```

In code they are subclasses of `aegis_core.errors.AegisError`.

## Configuration — `AEG-CFG`

| Code | What | Fix |
|---|---|---|
| `AEG-CFG-001` | Configuration error | Check `aegis.yaml`; see the message for the field. |
| `AEG-CFG-002` | Configuration file not found | `aegis init`, or pass the right `--config`. |
| `AEG-CFG-003` | Validation failed — bad field, unknown provider or provider type, missing `model`/`base_url`, unknown guardrail, bad pack option, or an unenforceable stage | Correct the field named in the message. |
| `AEG-CFG-010` | Secret reference can't be parsed or resolved | Use `secret://<backend>/<path>#<key>` and make sure the value exists (e.g. the env var is set). |
| `AEG-CFG-011` | Secret backend not registered | Use `env`, or register a `SecretProvider` for the scheme. |
| `AEG-CFG-020` | Plugin registry error | Check installed plugins are compatible and correctly packaged. |
| `AEG-CFG-021` | Two packages declare the same plugin name in one group | Uninstall or rename one. |
| `AEG-CFG-022` | Plugin not found — usually a `pack:` that isn't installed | `aegis plugin list`; install the pack. |

## Authentication — `AEG-AUTH`

| Code | HTTP | What | Fix |
|---|---|---|---|
| `AEG-AUTH-001` | 401 | No valid bearer key | Send `Authorization: Bearer aeg-…` from `aegis keys create`. |
| `AEG-AUTH-003` | 403 | Caller isn't on the paused run's approver list | Resume as a listed approver. |

## Server — `AEG-SRV`

| Code | What | Fix |
|---|---|---|
| `AEG-SRV-001` | `aegis serve` refused: no authenticator and no `--no-auth` | Create keys, or pass `--no-auth` for local development only. |

## Providers — `AEG-PRV`

| Code | What | Fix |
|---|---|---|
| `AEG-PRV-001` | Provider returned an unexpected error | Check configuration, credentials and model name. |
| `AEG-PRV-002` | Provider rejected the credentials | Update the key; check it hasn't expired. |
| `AEG-PRV-003` | Provider rate limit | Back off, raise your quota, or add another route. |
| `AEG-PRV-004` | Provider timed out | Check connectivity; raise the timeout. |
| `AEG-PRV-005` | Saved provider profile not found | `aegis provider list` / `aegis provider add`. |

## Policy lint — `AEG-POL`

| Code | What | Fix |
|---|---|---|
| `AEG-POL-000` | Config isn't valid YAML | Fix the syntax. |
| `AEG-POL-001` | Pipeline references an undeclared guardrail | Declare it under `guardrails:` or remove the reference. |
| `AEG-POL-002` | A guardrail's `pack:` isn't installed | Install the package that provides it. |
| `AEG-POL-003` | Egress guard is non-incremental; route will buffer | Informational — use an incremental guard if you need true streaming. |
| `AEG-POL-004` | `tool_call` / `tool_result` is set; `aegis serve` would refuse to start | Remove the key; govern tools in Python with `McpExecuteNode`. |
| `AEG-POL-005` | A provider's endpoint URL encodes a region that contradicts its `residency.region` | Fix the declaration or point at the right regional endpoint. |
| `AEG-POL-006` | An `exporters:` entry names a type that isn't installed | Install the exporter's package or fix `type`. |

## MCP — `AEG-MCP`

| Code | What | Fix |
|---|---|---|
| `AEG-MCP-001` | Can't reach or talk to the MCP server | Check the server URL and that it's running. |
| `AEG-MCP-002` | A tool-call guard blocked the call | Review the arguments against policy. |
| `AEG-MCP-003` | A tool-result guard blocked the result | Review the tool's output for injection patterns. |
| `AEG-MCP-004` | Tool not found on the MCP server | Check the name against the server's `tools/list`. |

## RAG — `AEG-RAG`

| Code | What | Fix |
|---|---|---|
| `AEG-RAG-001` | Vector store or embedder unreachable | Check the connection and that the service is up. |
| `AEG-RAG-002` | Namespace not found | Index at least one document into it. |
| `AEG-RAG-003` | Retrieved content blocked by an injection guard | Clean the indexed source documents. |
| `AEG-RAG-004` | Indexing failed | Check the store is writable and the embedder reachable. |
