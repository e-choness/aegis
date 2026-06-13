# Error codes

All Aegis errors follow the `AEG-<AREA>-<NNN>` format. Every error has a
`what` (symptom), `why` (cause), and `fix` (action to take).

## Config (`AEG-CFG-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-CFG-001 | Invalid YAML | Config file has a syntax error | Check the YAML syntax at the line indicated |
| AEG-CFG-002 | Unknown field | Unrecognised key in config | Remove the unknown field or check spelling |
| AEG-CFG-003 | Missing required field | A required config key is absent | Add the required field |
| AEG-CFG-010 | Unknown provider reference | Route references a provider not declared | Declare the provider under `providers:` |
| AEG-CFG-011 | Unknown guardrail reference | Pipeline references a guardrail not declared | Declare the guardrail under `guardrails:` |
| AEG-CFG-020 | Plugin load error | Entry-point package could not be loaded | Check the package is installed and the entry point is correct |
| AEG-CFG-021 | Duplicate plugin name | Two plugins declared the same name | Rename one plugin |
| AEG-CFG-022 | Plugin not found | Referenced plugin name has no registered provider | Install the plugin or fix the name |

## Auth (`AEG-AUTH-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-AUTH-001 | 401 Unauthorized | Bearer token missing or invalid | Pass a valid `aeg-...` key in `Authorization: Bearer` |
| AEG-AUTH-003 | 403 Forbidden | Principal not in run's `approvers` list | Use an authorised principal or update the approvers list |

## Provider (`AEG-PRV-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-PRV-001 | Provider not found | Named provider not in registry | Check the provider name matches an entry in `providers:` |
| AEG-PRV-002 | No compliant provider | All candidates filtered by residency policy | Add a compliant provider or relax the residency requirement |
| AEG-PRV-003 | Provider call failed | Upstream model API returned an error | Check the provider status and credentials |
| AEG-PRV-004 | Model not supported | Requested model not available on this provider | Choose a model from the provider's supported list |
| AEG-PRV-005 | Credential error | API key rejected by provider | Update the credential in your secrets backend |

## Policy (`AEG-POL-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-POL-001 | Broken guardrail reference | Config references an unknown guardrail pack | Install the pack or fix the `pack:` value |
| AEG-POL-002 | Missing policy pack | Required pack module not installed | Install the package, e.g. `pip install aegis-ai[pii]` |
| AEG-POL-003 | Streaming downgrade | Non-incremental egress guard on streaming route | Make the guard incremental or accept buffered mode |

## MCP (`AEG-MCP-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-MCP-001 | Tool call blocked | Tool-call guard blocked the request | Check the tool-call guard policy |
| AEG-MCP-002 | Tool result blocked | Tool-result guard blocked the response | Check the tool-result guard policy |
| AEG-MCP-003 | Tool not found | MCP server did not expose the requested tool | Check the MCP server configuration |
| AEG-MCP-004 | Exfiltration attempt | Tool arguments contain masked PII placeholders | PII is trying to leak through tool calls; check egress policy |

## RAG (`AEG-RAG-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-RAG-001 | RAG not configured | RAG endpoints called without a configured store | Configure `rag_store` in `aegis.yaml` |
| AEG-RAG-002 | Embedding error | Embedding provider failed | Check the embedding provider configuration |
| AEG-RAG-003 | Document blocked | Retrieved document blocked by tool-result guard | The document contains content blocked by policy |
| AEG-RAG-004 | Store error | Vector store operation failed | Check the vector store configuration and connectivity |

## Server (`AEG-SRV-*`)

| Code | What | Why | Fix |
|---|---|---|---|
| AEG-SRV-001 | Server startup error | Application failed to initialise | Check the startup log for details |
