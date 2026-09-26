<p align="center">
  <a href="https://e-choness.github.io/aegis/"><img src="https://raw.githubusercontent.com/e-choness/aegis/main/images/banner-wide.svg" alt="Aegis — the self-hosted AI gateway that shows its work" width="100%"></a>
</p>

# aegis-gateway

**Aegis** is a self-hosted AI gateway. It sits between your applications and
any LLM provider, runs every request through guardrails you declare in one
YAML file, and records every decision in a hash-chained audit ledger — so
*"why was this blocked, masked or paused, and who signed off?"* always has an
answer.

This is the umbrella package: the `aegis` CLI, the server, the kernel and all
first-party policy packs.

## Install

```bash
pip install aegis-gateway
python -m spacy download en_core_web_sm   # model used by the PII pack
```

Requires Python 3.12+.

## Sixty seconds to a governed endpoint

```bash
aegis init                                 # aegis.yaml: fake provider + PII masking
aegis serve --config aegis.yaml --no-auth  # http://localhost:8000
```

Point any OpenAI client at it — the `model` field selects an Aegis route:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dev")
reply = client.chat.completions.create(
    model="default",
    messages=[{"role": "user", "content": "Email jane@example.com the summary"}],
)
print(reply.choices[0].message.content)  # the model only ever saw <EMAIL_ADDRESS_0>
```

Then read the trail:

```bash
export AEGIS_SERVER_URL=http://localhost:8000
aegis explain --last                                    # verdict-by-verdict trail
aegis audit export -o ledger.jsonl && aegis audit verify ledger.jsonl
```

## Four verdicts, nothing else

| Verdict | What happens |
|---|---|
| `allow` | Continue unchanged. |
| `sanitize` | Continue with rewritten content. |
| `block` | Stop. The client gets a refusal; the ledger gets the reason. |
| `require_approval` | Checkpoint and pause until a named human approves or denies. |

## What's included

| Package | Provides |
|---|---|
| [`aegis-gateway-core`](https://pypi.org/project/aegis-gateway-core/) | Kernel: config, plugin registry, pipeline, contracts, test kits |
| [`aegis-gateway-server`](https://pypi.org/project/aegis-gateway-server/) | FastAPI server: OpenAI-compatible and native APIs, auth, ledger |
| [`aegis-gateway-cli`](https://pypi.org/project/aegis-gateway-cli/) | The `aegis` command |
| [`aegis-gateway-sdk`](https://pypi.org/project/aegis-gateway-sdk/) | Python client (sync + async) |
| [`aegis-gateway-pack-pii`](https://pypi.org/project/aegis-gateway-pack-pii/) | PII masking with Presidio |
| [`aegis-gateway-pack-residency`](https://pypi.org/project/aegis-gateway-pack-residency/) | Data-residency enforcement |
| [`aegis-gateway-pack-classification`](https://pypi.org/project/aegis-gateway-pack-classification/) | Content labelling |
| [`aegis-gateway-pack-budgets`](https://pypi.org/project/aegis-gateway-pack-budgets/) | Per-principal monthly spend caps |
| [`aegis-gateway-pack-llm-guard`](https://pypi.org/project/aegis-gateway-pack-llm-guard/) | LLM Guard scanners |

Install a subset instead if you only need part of it — e.g. `pip install
aegis-gateway-core` to build a plugin.

## Learn more

- [Documentation](https://e-choness.github.io/aegis/) — guide, policy packs, plugin development, reference
- [Changelog](https://e-choness.github.io/aegis/changelog) · [Releases](https://github.com/e-choness/aegis/releases)
- [Source & issues](https://github.com/e-choness/aegis)

Aegis is **alpha** software, licensed under [AGPL-3.0-or-later](https://github.com/e-choness/aegis/blob/main/LICENSE).
