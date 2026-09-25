# LLM Guard

`aegis.llm_guard` adapts [LLM Guard](https://llm-guard.com/) input scanners
into Aegis guardrails — model-based detection for prompt injection,
toxicity, secrets and more.

```yaml
guardrails:
  injection:
    pack: aegis.llm_guard
    scanners: [PromptInjection]   # default
    threshold: 0.8                # default; passed to each scanner

pipeline:
  ingress: [injection]
```

Each name in `scanners` is a class from `llm_guard.input_scanners`
(`PromptInjection`, `Toxicity`, `Secrets`, `BanTopics`, …). One guard is
created per scanner, named `llm_guard.<Scanner>`, and they run in order
against the latest message. A scanner that reports the input invalid blocks
the request with its risk score in the reason.

## Things to know

- LLM Guard downloads its models on first use and runs them locally; expect
  a slow first request and a large install footprint (PyTorch).
- Scanners are built per request. For high-traffic routes, prefer a cheap
  regex guard in front and reserve model-based scanners for routes that
  need them.
- These guards declare `streaming = "none"`; on egress they make a route
  buffer.
