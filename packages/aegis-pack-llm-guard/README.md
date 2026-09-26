# aegis-gateway-pack-llm-guard

Runs [LLM Guard](https://llm-guard.com/) input scanners (prompt injection,
toxicity, secrets, …) as Aegis guardrails.

```yaml
guardrails:
  injection:
    pack: aegis.llm_guard
    scanners: [PromptInjection]
    threshold: 0.8
pipeline:
  ingress: [injection]
```

See [LLM Guard](https://e-choness.github.io/aegis/packs/llm-guard).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
