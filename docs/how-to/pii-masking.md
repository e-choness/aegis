# How-to: PII masking

Aegis's PII pack masks personally identifiable information in ingress messages
and unmasks it in the model's response — the model never sees real PII.

## Install

```bash
pip install "aegis-gateway[pii]"
python -m spacy download en_core_web_sm
```

## Configure

```yaml
providers:
  main:
    type: anthropic
    api_key: secret://env/ANTHROPIC_API_KEY

guardrails:
  pii:
    pack: aegis.pii
    mode: mask

pipeline:
  ingress: [pii]
  egress: [pii.unmask]

routes:
  default:
    provider: main
```

The ingress stage replaces detected entities with placeholders like
`<PERSON_1>`, `<EMAIL_ADDRESS_1>`. The egress stage substitutes them back in
the response using the per-run mask map (never serialised into model-visible
messages).

## Supported entity types

The PII pack uses [Presidio](https://microsoft.github.io/presidio/) + the
`en_core_web_sm` spaCy model. Detected by default:

- `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `LOCATION`, `CREDIT_CARD`,
  `IBAN_CODE`, `IP_ADDRESS`, `URL`, `US_SSN`, `DATE_TIME`

## Audit events

Every masking and unmasking operation emits an event into the run's event log.
Query it via:

```bash
curl http://localhost:8000/v1/audit
```

## Testing without PII installed

In unit tests, use `FakeProvider` and skip PII installation:

```python
import pytest

pytest.importorskip("presidio_analyzer", reason="[pii] extra not installed")
```
