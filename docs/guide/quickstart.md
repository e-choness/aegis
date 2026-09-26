# Quickstart

In a few minutes you will run a local gateway, send it a request that gets
PII-masked on the way in, read the verdict trail, and then swap in a real
model.

## 1. Install

Aegis needs **Python 3.12+**.

::: code-group

```bash [pip]
pip install aegis-gateway
python -m spacy download en_core_web_sm   # model used by the PII pack
```

```bash [uv]
uv tool install aegis-gateway
uv run python -m spacy download en_core_web_sm
```

```bash [From source (Docker)]
git clone https://github.com/e-choness/aegis && cd aegis
docker compose build dev
docker compose run --rm dev uv sync --all-packages
# prefix every command below with: docker compose run --rm dev uv run
```

:::

`aegis-gateway` is the umbrella package: CLI, server, core and all first-party
policy packs.

## 2. Generate a config

```bash
aegis init
```

This writes `aegis.yaml` with a **`fake` provider** (canned responses, no
credentials) and **PII masking** switched on:

```yaml
providers:
  default:
    type: fake
    complete_response: "[aegis] hello — replace this provider with a real one"

guardrails:
  pii:
    pack: aegis.pii
    mode: mask

pipeline:
  ingress: [pii]
  egress: [pii]

routes:
  default:
    provider: default

auth:
  type: none
```

Check it any time with `aegis config validate aegis.yaml` and
`aegis policy lint aegis.yaml`.

## 3. Start the gateway

```bash
aegis serve --config aegis.yaml --no-auth
```

`--no-auth` is required when no keys exist yet — `aegis serve` refuses to
start without an authenticator otherwise. The server listens on
`http://localhost:8000` and creates `aegis_ledger.db`, `aegis_runs.db` and
`aegis_checkpoints.db` in the working directory.

## 4. Send a request

```bash
curl -s http://localhost:8000/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"route": "default", "messages": [{"role": "user", "content": "Call Jane Doe at 416-555-0199"}]}'
```

The response carries the run's `events` — the PII pack's mask node on
ingress, the provider call, and the unmask node on egress. The model only
ever saw placeholders like `<PERSON_0>` and `<PHONE_NUMBER_0>`.

The same route is reachable through the OpenAI-compatible endpoint:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dev")
reply = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(reply.choices[0].message.content)
```

## 5. Read the trail

The CLI talks to a running server through `AEGIS_SERVER_URL` (default
`http://localhost:8767`) and `AEGIS_API_KEY`:

```bash
export AEGIS_SERVER_URL=http://localhost:8000
aegis explain --last        # verdict trail of the most recent run
aegis report summary        # route inventory, run stats, ledger length
```

## 6. Use a real model

Replace the `fake` provider. Credentials are never written inline — they are
`secret://` references resolved from the environment at load time:

::: code-group

```yaml [OpenAI-compatible (Ollama, vLLM, OpenAI…)]
providers:
  default:
    type: openai_compatible
    base_url: http://localhost:11434/v1
    model: llama3.1
    api_key: secret://env/OPENAI_API_KEY#value
```

```yaml [Anthropic]
providers:
  default:
    type: anthropic
    model: anthropic/claude-sonnet-5
    api_key: secret://env/ANTHROPIC_API_KEY#value
```

:::

::: tip The `#key` fragment is required
Secret URIs have the shape `secret://<backend>/<path>#<key>`. The `env`
backend reads the variable named by `<path>` and ignores the key, but the
fragment must be present for the URI to parse.
:::

## 7. Turn on authentication

```bash
aegis keys create alice --team platform   # prints aeg-… once; only the hash is stored
aegis serve --config aegis.yaml           # no --no-auth: API keys are now required
```

Clients send `Authorization: Bearer aeg-…`. Keys live in
`~/.aegis/keys.json` by default (`--keys-file` to change).

## Where next

- [Core concepts](./concepts) — what actually happens to a request.
- [Human approvals](./approvals) — make a guardrail pause instead of block.
- [Policy packs](/packs/) — what ships in the box.
