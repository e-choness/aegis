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
  egress: [pii]     # PiiRedactNode → "pii.redact", then PiiUnmaskNode → "pii.unmask"
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

### Personal data the model produces itself

On the way out, `pii.redact` looks at the reply **before** the user's values
are restored. At that point everything the user sent is still a placeholder,
so any personal data it finds came from the model — a phone number from its
training data, an address from a retrieved document. Each one is replaced
with a label that is never restored, and the run records a `sanitize`:

| Step | Text |
|---|---|
| Model replies | `Sent to <EMAIL_ADDRESS_0>. Our fraud line is 416-555-0199.` |
| After `pii.redact` | `Sent to <EMAIL_ADDRESS_0>. Our fraud line is [PHONE_NUMBER].` |
| Client receives | `Sent to jane@example.com. Our fraud line is [PHONE_NUMBER].` |

```yaml
guardrails:
  pii:
    pack: aegis.pii
    redact_output: true                       # default
    redact_entities: [EMAIL_ADDRESS, CA_SIN]  # default: the default entities except PERSON
```

Names aren't redacted by default: models mention them constantly (authors,
public figures, "Jane" in an example) and name detection is the least precise.
Add `PERSON` to `redact_entities` for routes that must never name anyone.
`redact_output: false` turns the step off.

### Where the restore happens

`egress: [pii]` places redact and unmask together. To run another egress
check on the reply while it still holds placeholders — so that check never
sees the user's personal data — name the two steps separately and put it
between them:

```yaml
pipeline:
  ingress: [pii]
  egress: [pii.redact, my_output_check, pii.unmask]
```

To keep the placeholders in the reply — a route whose output goes to a third
party rather than back to the person who wrote the prompt — set
`unmask_response: false` on the route. It removes every restore step (this
pack's and the [content pack](./content)'s); redaction still runs.

```yaml
providers:
  llm:
    type: fake

routes:
  outbound_email:
    provider: llm
    unmask_response: false
```

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

**Default entities:** `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`,
`STREET_ADDRESS`, `POSTAL_CODE`, `IP_ADDRESS`, `CREDIT_CARD`, `IBAN_CODE`, `CRYPTO`, `US_SSN`, `US_ITIN`,
`US_PASSPORT`, `US_BANK_NUMBER`, `UK_NHS`, `CA_SIN`,
`MEDICAL_LICENSE`.

**Opt-in:** `LOCATION` (addresses — also every city in a travel or weather
question), `DATE_TIME` (dates of birth — also weekdays and "quarterly"),
`URL`, `NRP`, `US_DRIVER_LICENSE`, and region-specific IDs (`AU_*`, `IN_*`,
`SG_NRIC_FIN`).

**Places.** A city or country identifies no one, so `LOCATION` is opt-in. What
pinpoints a household is masked by default:

| Entity | Matches |
|---|---|
| `STREET_ADDRESS` | a house number on a named street — `42 Wellington Street West`, `Apt 4B, 1187 Queen St E`, `45 rue Sainte-Catherine` — and `PO Box 4410` |
| `POSTAL_CODE` | Canadian (`M4M 1K8`), UK (`SW1A 2AA`), US ZIP+4 (`02139-4307`) or state + ZIP (`NY 10118`) |

Street words must be capitalised, so "drove 300 km down the highway" or
"chapter 3" isn't an address. A bare five-digit number isn't treated as a ZIP
code — too many things are five digits.

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
