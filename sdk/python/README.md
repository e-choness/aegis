# aegis-gateway-sdk

Python client for the Aegis gateway — sync (`AegisClient`) and async
(`AsyncAegisClient`), covering runs, approvals, audit and chat.

```bash
pip install aegis-gateway-sdk
```

```python
from aegis_sdk import AegisClient

with AegisClient(base_url="http://localhost:8000", api_key="aeg-...") as client:
    run = client.create_run(
        [{"role": "user", "content": "Wire $40k to vendor 7731"}],
        route="payments",
        approvers=["jane"],
    )
    print(run.run_id, run.status)
```

For plain chat, any OpenAI SDK works against Aegis too. See [SDKs](https://e-choness.github.io/aegis/reference/sdks).

## Links

- [Documentation](https://e-choness.github.io/aegis/) · [Changelog](https://github.com/e-choness/aegis/blob/main/CHANGELOG.md) · [Source](https://github.com/e-choness/aegis)
- Most users want the umbrella package: `pip install aegis-gateway`.

Part of [Aegis](https://pypi.org/project/aegis-gateway/), a self-hosted AI gateway. MIT licensed.
