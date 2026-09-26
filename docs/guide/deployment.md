# Deploying

`aegis serve` is a single process: FastAPI on uvicorn, a SQLite evidence
ledger, and a SQLite checkpointer for paused runs. This page covers running
it safely.

## Checklist

- [ ] Authentication on — no `--no-auth` outside localhost.
- [ ] Provider credentials as `secret://` references, never inline.
- [ ] TLS terminated in front of Aegis, with response buffering **off** for SSE.
- [ ] `aegis_ledger.db`, `aegis_runs.db` and `aegis_checkpoints.db` on persistent storage and backed up.
- [ ] `/metrics` reachable only from your monitoring network.
- [ ] Residency-sensitive deployments pair the residency pack with network egress controls.

## Run it

```bash
aegis serve --config /etc/aegis/aegis.yaml \
  --host 0.0.0.0 --port 8000 \
  --keys-file /var/lib/aegis/keys.json \
  --ledger-db /var/lib/aegis/ledger.db \
  --runs-db /var/lib/aegis/runs.db \
  --checkpoint-db /var/lib/aegis/checkpoints.db
```

The process refuses to start (`AEG-SRV-001`) if no authenticator is
configured and `--no-auth` isn't given.

## Identity and keys

Clients hold Aegis keys, never provider credentials.

```bash
aegis keys create svc-underwriting --team risk --keys-file /var/lib/aegis/keys.json
aegis keys list   --keys-file /var/lib/aegis/keys.json
aegis keys revoke <key-id> --keys-file /var/lib/aegis/keys.json
```

A key looks like `aeg-<64 hex>`, is printed exactly once, and only its
SHA-256 hash is stored. It resolves to a principal (`id`, `team`) that is
attached to every run, checked against approver lists, and used by
per-principal packs such as budgets.

Aegis is **single-tenant by design**: one config, one policy, many
principals. Run separate instances for separate tenants.

## Secrets

`secret://<backend>/<path>#<key>` URIs are resolved when the config is
loaded; resolved values are held as `SecretStr` and redacted from
`aegis config show`, logs and the config digest.

| Backend | Example | Notes |
|---|---|---|
| `env` | `secret://env/ANTHROPIC_API_KEY#value` | Enabled by default in `aegis serve`. `<key>` is ignored but required. |
| `keyring` | `secret://keyring/aegis/anthropic#api_key` | OS keychain; register `KeyringSecretProvider` when loading config yourself. |
| custom | `secret://vault/prod/llm#anthropic` | Implement `SecretProvider` — see [Write a plugin](/develop/plugins#secret-backends). |

Any config value can also be overridden with `AEGIS__SECTION__KEY`
environment variables, e.g. `AEGIS__ROUTES__DEFAULT__MODEL=gpt-4o`.

## Docker

A minimal image for your own deployment:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir aegis-gateway \
 && python -m spacy download en_core_web_sm
WORKDIR /srv/aegis
COPY aegis.yaml .
VOLUME ["/var/lib/aegis"]
EXPOSE 8000
CMD ["aegis", "serve", "--config", "aegis.yaml", \
     "--keys-file", "/var/lib/aegis/keys.json", \
     "--ledger-db", "/var/lib/aegis/ledger.db", \
     "--runs-db", "/var/lib/aegis/runs.db", \
     "--checkpoint-db", "/var/lib/aegis/checkpoints.db"]
```

The public demo on Hugging Face Spaces is built the same way — see
`deploy/huggingface/` in the repository, which the release workflow uploads
to the Space after every PyPI release.

## Public demos

`aegis serve --demo` adds safety rails for an internet-facing, no-auth
instance: each visitor (identified by the first `X-Forwarded-For` hop) may
run 10 prompts a minute, with a rolling cap of 600 an hour across everyone.
Reads, pages and `/v1/health` are never limited. Only use it behind a proxy
you trust to set `X-Forwarded-For`.

## Behind a reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name aegis.example.com;

    ssl_certificate     /etc/ssl/aegis.crt;
    ssl_certificate_key /etc/ssl/aegis.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;   # required for SSE streaming
        proxy_cache off;
    }

    location /metrics {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

## Observability

Prometheus metrics are served at `/metrics` without authentication, and each
run is wrapped in an OpenTelemetry span (`aegis.run`) on the process's global
tracer provider. Aegis doesn't configure an exporter itself: install
`opentelemetry-distro` plus an exporter and start the server under
`opentelemetry-instrument aegis serve …`, or set a tracer provider in your
own entry point. The repo's `docker compose --profile observability up`
starts Prometheus (`:9090`) and Grafana (`:3000`). Details in
[Metrics & traces](/reference/observability).

## Data you should keep

| File | Contains | Loss means |
|---|---|---|
| `ledger.db` | Hash-chained evidence | Audit history gone; export regularly with `aegis audit export`. |
| `runs.db` | Run records, statuses and event logs | `aegis explain`, `/v1/audit` and resuming paused runs stop working for past runs. |
| `checkpoints.db` | Paused-run state | Paused runs can no longer be resumed. |
| `keys.json` | Key hashes and principals | Every client needs a new key. |

Paused runs need both `runs.db` and `checkpoints.db` to be resumable after a
restart.
