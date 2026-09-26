# Streaming

Egress guards want the whole response; streaming wants to forward tokens
immediately. Aegis resolves this **per route, at startup**, and never
silently: each route is either *true-streaming* or *buffered*, and the wire
format is valid OpenAI SSE either way.

## How a route's mode is chosen

Each guardrail declares `streaming = "none"` or `"incremental"`.

- **All egress guards incremental → true streaming.** Provider chunks are
  forwarded as they arrive, each one scanned with `scan_chunk()` first. When
  the provider finishes, every guard's `finalize()` sees the full text
  before the `stop` frame is sent.
- **Any egress guard `"none"`, or any egress node that doesn't declare
  `stream_capability` → buffered.** The whole pipeline runs, then the result
  is replayed as SSE frames. Clients see latency, never protocol errors.
  Transformation nodes (PII unmasking, budget recording) buffer by design:
  they need the complete response.

**Ingress always runs first**, in either mode — the provider only ever
streams the ingress-processed (e.g. masked) messages. Streamed runs are
recorded in the run store and ledger exactly like non-streamed ones.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Aegis
    participant G as Incremental egress guard
    participant P as Provider
    C->>A: POST /v1/chat/completions (stream: true)
    A->>P: stream
    loop every chunk
        P-->>A: chunk
        A->>G: scan_chunk(chunk)
        G-->>A: allow
        A-->>C: data: {delta}
    end
    A->>G: finalize(full_text)
    alt late violation
        G-->>A: block
        A-->>C: finish_reason: content_filter · aegis_event: late_violation
    else clean
        G-->>A: allow
        A-->>C: finish_reason: stop
    end
    A-->>C: data: [DONE]
```

A block from `scan_chunk()` ends the stream immediately with
`finish_reason: "content_filter"` and `aegis_event: "stream_violation"`.

If an **ingress** node blocks or pauses the request, no provider call is made
and the stream is a single terminal frame: `finish_reason: "content_filter"`,
`aegis_event` set to `blocked`, `paused` or `denied`, and `aegis_run_id` so a
paused run can be approved with `aegis runs approve <id>`.

## Find out which mode you got

```bash
aegis policy lint aegis.yaml
```

`AEG-POL-003` is reported for every egress guard that forces a route to
buffer. It is informational — buffering is a legitimate choice when a guard
needs full context.

## Writing an incremental guard

```python
from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class NoCodenamesGuard:
    name = "no_codenames"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return await self.finalize(state.response or "")

    async def scan_chunk(self, chunk: str) -> Verdict:
        if "PROJECT-ORCA" in chunk:
            return Verdict.block("codename leaked")
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        # Catches a codename split across two chunks.
        if "PROJECT-ORCA" in accumulated:
            return Verdict.block("codename leaked")
        return Verdict.allow()
```

`scan()` is still required — buffered routes and non-streaming requests use
it.
