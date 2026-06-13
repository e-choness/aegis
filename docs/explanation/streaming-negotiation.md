# Streaming negotiation

Egress guards want the complete output; streaming wants to emit tokens
immediately. Aegis refuses to resolve this tension silently.

## The options we rejected

**Always buffer** gives full guard fidelity and a broken-feeling product next
to every streaming provider. **Always stream with windowed scanning** gives
good UX while silently weakening guards that need full context — the user has
no idea their policy is running at reduced fidelity. Both fail the same test:
the developer is not making an informed choice.

## Capability negotiation

Every guardrail declares `streaming: none | incremental`. Incremental guards
implement `scan_chunk()` plus a mandatory `finalize()` full-text pass;
non-incremental guards only implement `scan()`. At compile time the graph
assembler computes each route's mode:

- **All egress guards incremental** → true streaming with a hold-back window
  (tokens are released a small window behind generation). If `finalize()`
  surfaces a late violation, the stream is truncated and a violation event is
  logged.
- **Any guard non-incremental** → the route buffers.

The trade-off is visible, not silent: `aegis policy lint` reports every
downgrade — *"route `default` cannot stream because `toxicity_ml` declares
streaming=none."* Choosing latency over a full-context scanner (or vice versa)
is the developer's call, made with eyes open.

## The wire never breaks

A buffered route asked for `stream: true` still answers with valid OpenAI SSE
frames — the scanned result emitted as chunks after the guard pass. Clients
built on OpenAI SDKs perceive latency, never protocol errors.
