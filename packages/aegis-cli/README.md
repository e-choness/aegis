# aegis-gateway-cli

The `aegis` command-line tool.

```bash
aegis init                      # starter aegis.yaml
aegis serve --no-auth           # run the gateway
aegis policy lint               # check a config before deploying
aegis explain --last            # verdict trail of the latest run
aegis runs approve <run-id>     # resume a paused run
aegis audit export -o l.jsonl && aegis audit verify l.jsonl
aegis plugin new my-guard --kind guardrail
```

See the [CLI reference](https://e-choness.github.io/aegis/reference/cli).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
