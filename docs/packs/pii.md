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
| User sends | `Please write to Jane Doe at jane@example.com` |
| Model receives | `Please write to <PERSON_0> at <EMAIL_ADDRESS_0>` |
| Model replies | `Drafted a note to <PERSON_0>.` |
| Client receives | `Drafted a note to Jane Doe.` |

The placeholder → value map lives in `RunState.mask_map`. It is never put in
model-visible messages and is stripped from events before they reach the
ledger — the ledger records entity *types and counts*, not values.

Placeholders are allocated per run in reading order, and a value that
appears more than once — in one message or across the conversation — always
gets the same placeholder, so the model can tell two mentions are the same
person. When detections overlap, the most confident one wins — pattern
matches such as emails, cards and SINs beat spaCy's statistical name guesses —
and ties go to the wider span.

## Tuning detection

Presidio knows many entity types, and several of them are noisy: `DATE_TIME`
matches "Monday" and "quarterly", `US_DRIVER_LICENSE` matches "Q3". So by
default Aegis masks only **identifying** entities, above a confidence
threshold:

```yaml
guardrails:
  pii:
    pack: aegis.pii
    mode: mask
    threshold: 0.4                  # minimum confidence, 0–1 (default 0.4)
    entities: [PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CA_SIN, DATE_TIME]
    allow_list: [Aegis, Claude]     # exact strings that are never masked
```

| Option | Default | Notes |
|---|---|---|
| `entities` | the identifying set below | A list of entity types, or `ALL` for every recognizer. Unknown names fail at startup with the supported list. |
| `threshold` | `0.4` | Phone numbers without context score 0.40 — raising the threshold above that stops masking them. |
| `allow_list` | none | Product names, your company, public contacts. |
| `spacy_model` | `en_core_web_sm` | spaCy model for names and locations. Must be installed (`python -m spacy download <model>`) — Aegis never downloads one at runtime, and a missing model fails at startup. `en_core_web_lg` (~560 MB) rarely finds more for the default entities. |

**Default entities:** `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `LOCATION`,
`IP_ADDRESS`, `CREDIT_CARD`, `IBAN_CODE`, `CRYPTO`, `US_SSN`, `US_ITIN`,
`US_PASSPORT`, `US_BANK_NUMBER`, `UK_NHS`, `CA_SIN`,
`MEDICAL_LICENSE`.

**Opt-in:** `DATE_TIME` (dates of birth — also weekdays and "quarterly"),
`URL`, `NRP`, `US_DRIVER_LICENSE`, and region-specific IDs (`AU_*`, `IN_*`,
`SG_NRIC_FIN`).

`CA_SIN` is added by Aegis — Presidio has no Canadian recognizer. It matches
nine digits (optionally grouped `123-456-789`) and keeps only numbers that
pass the SIN checksum.

The same options apply in `detect` mode.

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

- Detection is English-only (`language="en"`); names are found by spaCy's
  statistical model, so an occasional capitalised word ("Email …" at the start
  of a sentence) is read as a name — add such words to `allow_list`.
- The first request after start-up loads the spaCy model and can take
  several seconds.
- The egress unmask node needs the complete response, so routes that
  unmask buffer streamed responses (see [Streaming](/guide/streaming)).
