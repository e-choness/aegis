# LLM Guard

`aegis.llm_guard` adapts [LLM Guard](https://protectai.github.io/llm-guard/) input scanners
into Aegis guardrails — model-based detection for prompt injection,
toxicity, secrets and more.

The pack ships with `aegis-gateway`, but the LLM Guard library itself (and
PyTorch, which it pulls in) is opt-in:

```bash
pip install "aegis-gateway-pack-llm-guard[llm-guard]"
```

Without it, a config that enables `aegis.llm_guard` fails at startup with that
install hint.

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

- **Security:** LLM Guard's last release (0.3.16, May 2025) pins exact
  versions of `transformers` and `json-repair` that have known advisories,
  and an older Presidio. Installing the extra brings those versions into your
  environment. Prefer the [PII pack](./pii) and regex guards unless you need
  its model-based scanners, and keep an eye on upstream for a new release.

- LLM Guard downloads its models on first use and runs them locally; expect
  a slow first request and a large install footprint (PyTorch).
- Scanners are built per request. For high-traffic routes, prefer a cheap
  regex guard in front and reserve model-based scanners for routes that
  need them.
- These guards declare `streaming = "none"`; on egress they make a route
  buffer.
