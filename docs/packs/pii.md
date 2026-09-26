# PII masking

`aegis.pii` uses [Microsoft Presidio](https://microsoft.github.io/presidio/)
with spaCy's `en_core_web_sm` model to find personal data. In `mask` mode
**the model never sees it**: entities are swapped for placeholders on the way
in and restored on the way out.

```bash
python -m spacy download en_core_web_sm   # once per environment
```

## Mask mode (default)

```yaml
guardrails:
  pii:
    pack: aegis.pii
    mode: mask

pipeline:
  ingress: [pii]    # PiiMaskNode   → "pii.mask"
  egress: [pii]     # PiiUnmaskNode → "pii.unmask"
```

| Step | Text |
|---|---|
| User sends | `Email Jane Doe at jane@example.com` |
| Model receives | `Email <PERSON_0> at <EMAIL_ADDRESS_0>` |
| Model replies | `Drafted a note to <PERSON_0>.` |
| Client receives | `Drafted a note to Jane Doe.` |

The placeholder → value map lives in `RunState.mask_map`. It is never put in
model-visible messages and is stripped from events before they reach the
ledger — the ledger records entity *types and counts*, not values.

Numbering is per run, so the same person gets the same placeholder across
every message in that run. Overlapping detections are resolved in favour of
the larger span.

## Detect mode

```yaml
guardrails:
  pii_block:
    pack: aegis.pii
    mode: detect

pipeline:
  ingress: [pii_block]
```

Instead of masking, a guard **blocks** any request that contains PII.
Use it on routes that must never receive personal data at all.

## Pairs well with

- **Tool governance** — `ExfiltrationGuard` blocks tool calls whose
  arguments contain a placeholder, so masked data can't be smuggled out
  through a tool. See [Tool governance](/guide/tool-governance).
- **Classification** — route or block on `labels["classification"] == "pii"`.

## Notes

- Detection is English-only (`language="en"`).
- The first request after start-up loads the spaCy model and can take
  several seconds.
- The egress unmask node needs the complete response, so routes that
  unmask buffer streamed responses (see [Streaming](/guide/streaming)).
