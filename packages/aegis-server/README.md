# aegis-gateway-server

The Aegis HTTP server (FastAPI): OpenAI-compatible `/v1/chat/completions`
and `/v1/models`, the native `/v1/runs` API with human approvals, API-key
authentication, the hash-chained evidence ledger, Prometheus metrics and
OpenTelemetry spans.

It is normally started with `aegis serve` from
[`aegis-gateway-cli`](https://pypi.org/project/aegis-gateway-cli/). To embed
it, build an executor and call `aegis_server.app.create_app(executor, ...)`.

See the [REST API reference](https://e-choness.github.io/aegis/reference/rest-api).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
