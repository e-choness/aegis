# The dependency doctrine: adopt, wrap, or write

Every dependency in Aegis carries one of three designations, recorded in the
project spec. Nothing enters the tree without one.

## Adopt

Use the library's public interface directly as our contract. Justified only
when the interface is itself a standard whose ecosystem we want plugin authors
to inherit: LangGraph's graph and checkpointer, the official MCP SDK,
OpenTelemetry, FastAPI, pydantic. Adopting means programming against that
ecosystem on purpose — a feature, not a leak.

## Wrap

Use it behind an Aegis Protocol, imported in **exactly one module**, version
pinned. For anything that moves fast or that we may swap: LiteLLM (the default
`ModelProvider` backend), LLM Guard (the default guardrail adapter), Presidio
(the PII pack). A wrapped dependency breaking is a one-file fix; nothing else
in the codebase knows it exists.

## Write

Only where no good wheel exists and the surface is small: the entry-point
registry glue, the graph assembler, the verdict spine, `secret://` resolution,
key hashing. If a "write" item grows past thin glue, that is a design smell to
revisit.

## Why this is enforced, not aspirational

The import-linter contract in CI fails the build if a wrapped library is
imported outside its adapter module, or if a policy pack imports anything but
public `aegis` APIs. Doctrine that is not executable is opinion.

One consequence worth naming: tiered extras. The slim install
(`pip install aegis-ai`) carries the kernel, server, and CLI only. Heavy
dependencies (spaCy models, transformers) arrive only with the pack that needs
them (`[pii]`, `[llm-guard]`, `[rag]`). A framework whose install pulls torch
before the first request would contradict everything above.
