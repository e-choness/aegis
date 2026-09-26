# SDKs

For plain chat, any **OpenAI SDK** works — set `base_url` to your gateway
and use the route name as `model`. Use the Aegis client when you need what
OpenAI's API can't express: approver lists, background runs, resume, audit
and ledger access. It's first-party for Python; for other languages, generate
one from the OpenAPI spec (below).

The Python SDK defaults to `http://localhost:8767`; pass your server's URL.

## Python — `aegis-gateway-sdk`

```bash
pip install aegis-gateway-sdk      # also installed with aegis-gateway
```

```python
from aegis_sdk import AegisClient

with AegisClient(base_url="http://localhost:8000", api_key="aeg-...") as client:
    run = client.create_run(
        [{"role": "user", "content": "Summarise Q3 for the board"}],
        route="default",
        approvers=["jane"],
    )
    if run.status == "paused":
        print("waiting for approval:", run.run_id)

    for chunk in client.stream_chat(
        [{"role": "user", "content": "Hi"}], model="default"
    ):
        print(chunk["choices"][0]["delta"].get("content", ""), end="")
```

`AsyncAegisClient` has the same methods as coroutines (`async with`,
`aclose()`).

| Method | Endpoint |
|---|---|
| `create_run(messages, *, route, background, approvers)` | `POST /v1/runs` |
| `get_run(run_id)` | `GET /v1/runs/{id}` |
| `resume_run(run_id, decision)` | `POST /v1/runs/{id}/resume` |
| `list_runs(*, principal, route, since)` | `GET /v1/audit` |
| `list_ledger(*, since_seq, route)` | `GET /v1/audit/ledger` |
| `inventory_records(*, route)` | `GET /v1/audit/inventory` |
| `audit_report()` | `GET /v1/audit/report` |
| `chat(messages, *, model)` | `POST /v1/chat/completions` |
| `stream_chat(messages, *, model)` | `POST /v1/chat/completions` (SSE) |

The default timeout is 60 s (model calls and first-use model loading are
slow); override with `timeout=`. HTTP errors raise `httpx.HTTPStatusError`.

## Other languages

Generate a client from [`openapi.json`](https://github.com/e-choness/aegis/blob/main/openapi.json):

```bash
docker compose --profile codegen run --rm codegen generate \
  -i /workspace/openapi.json -g go -o /workspace/.tmp/go-client
```

After changing an endpoint, regenerate the spec with
`docker compose run --rm dev uv run python scripts/export_openapi.py`.
