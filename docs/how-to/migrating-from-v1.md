# How-to: Migrating from v1

Aegis v2 is a substantial rewrite. This guide covers the key breaking changes
and migration paths. The v1 codebase is available at the `v1-legacy` git tag.

## Breaking changes summary

| Area | v1 | v2 |
|---|---|---|
| Pipeline | Custom call chain | LangGraph `StateGraph` |
| Config | `aegis_config.json` | `aegis.yaml` (pydantic v2) |
| Guardrails | `filter(text) -> bool` | `scan(messages, state) -> Verdict` |
| Providers | Direct LiteLLM call | `ModelProvider` protocol |
| Secrets | Plain strings in config | `secret://` URIs, `SecretStr` |
| Streaming | Not supported | True streaming + buffered fallback |
| HITL | Not supported | LangGraph interrupt + checkpointer |
| SDKs | None | Python + TypeScript |

## Config migration

v1 `aegis_config.json`:

```json
{
  "provider": "anthropic",
  "api_key": "sk-ant-...",
  "guardrails": ["regex_filter"]
}
```

v2 `aegis.yaml` equivalent:

```yaml
providers:
  main:
    type: anthropic
    api_key: secret://env/ANTHROPIC_API_KEY

guardrails:
  injection:
    pack: aegis.regex_guard

pipeline:
  ingress: [injection]

routes:
  default:
    provider: main
```

Move `api_key` to an environment variable and reference it via `secret://env/`.

## Guardrail migration

v1 guardrail:

```python
def filter_request(text: str) -> bool:
    return "bad_word" not in text
```

v2 guardrail:

```python
from aegis_core.pipeline import Verdict


class MyGuard:
    name = "my-guard"
    streaming = "none"

    async def scan(self, messages, state):
        text = " ".join(m.get("content", "") for m in messages)
        if "bad_word" in text:
            return Verdict.block("Blocked by my-guard")
        return Verdict.allow()
```

The key differences:

- Receives the full `messages` list (not a single string) — supports role-aware filtering
- Returns a `Verdict` instead of a bool — four options, not two
- `async` — the guardrail contract is fully async
- Declares `streaming` capability

## Provider migration

v1 used LiteLLM directly. v2 wraps it behind a `ModelProvider` protocol:

```python
from pydantic import SecretStr

from aegis_core.providers import LiteLLMProvider

provider = LiteLLMProvider(
    name="my-anthropic",
    model="claude-sonnet-4-5",
    api_key=SecretStr("..."),
)
```

Or use `openai_compatible` for any OpenAI-compatible endpoint.

## Testing migration

v2 ships contract test kits for every protocol:

```python
from aegis_core.testing import GuardrailContractKit

kit = GuardrailContractKit(MyGuard())  # noqa: F821
kit.assert_blocks(["bad_word message"])
kit.assert_allows(["clean message"])
```

## Getting help

Open a migration issue at [aegis-ai/aegis](https://github.com/aegis-ai/aegis/issues)
with the `migration` label.
