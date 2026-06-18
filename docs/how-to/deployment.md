# How-to: Deployment

## Single node

Install and run directly:

```bash
pip install aegis-gateway
aegis serve --host 0.0.0.0 --port 8000
```

`aegis serve` refuses to start unless an authenticator is configured in
`aegis.yaml`. Use `--no-auth` only in trusted internal networks.

## Docker Compose

The repository ships a `docker-compose.demo.yml` for a full demo stack
(Aegis + Open WebUI):

```bash
docker compose -f docker-compose.demo.yml up
# Open http://localhost:3000 — governed chat via Open WebUI
# Open http://localhost:8000/approvals — HITL approvals UI
```

For production, use the main `docker-compose.yml` which includes optional
observability (Prometheus + Grafana):

```bash
docker compose --profile observability up
```

## Reverse proxy (nginx)

Place Aegis behind nginx for TLS termination:

```nginx
server {
    listen 443 ssl;
    server_name aegis.example.com;

    ssl_certificate /etc/ssl/aegis.crt;
    ssl_certificate_key /etc/ssl/aegis.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE requires buffering disabled
        proxy_buffering off;
        proxy_cache off;
    }
}
```

!!! warning
    Disable proxy buffering (`proxy_buffering off`) for SSE streaming to work
    correctly. Without it, streaming responses are held until the connection
    closes.

## Postgres (production persistence)

SQLite (dev default) is single-process only. For production:

```yaml
persistence:
  type: postgres
  url: secret://env/DATABASE_URL
```

The Postgres instance hosts both the run store (SQLAlchemy) and LangGraph
checkpoints (pgvector-compatible). Run Alembic migrations before first start:

```bash
aegis db migrate
```

## Observability

Aegis emits OpenTelemetry traces from every run. Configure an exporter:

```yaml title="aegis.yaml"
telemetry:
  exporter: otlp
  endpoint: http://otel-collector:4317
```

Prometheus metrics are available at `/metrics` (no auth). Scrape config:

```yaml
scrape_configs:
  - job_name: aegis
    static_configs:
      - targets: ['aegis:8000']
```

## Security checklist

- [ ] `aegis serve` with an `api_key` authenticator (not `--no-auth`)
- [ ] TLS termination at the reverse proxy
- [ ] Provider credentials in a secrets backend, not plain env vars in prod
- [ ] Residency pack + egress allowlisting for data-sovereignty requirements
- [ ] `/metrics` endpoint access-restricted at the network layer
- [ ] Regular `aegis keys list` audit of active virtual keys
