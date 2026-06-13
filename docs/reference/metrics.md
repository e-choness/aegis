# Metrics & spans

Aegis emits Prometheus metrics and OpenTelemetry traces from every run.

## Prometheus metrics

Available at `GET /metrics` (no authentication required).

| Metric | Type | Labels | Description |
|---|---|---|---|
| `aegis_runs_total` | Counter | `route`, `status` | Total number of governed runs |
| `aegis_run_duration_seconds` | Histogram | `route`, `status` | Run duration in seconds |

### Scrape configuration

```yaml
scrape_configs:
  - job_name: aegis
    static_configs:
      - targets: ['aegis:8000']
    scrape_interval: 15s
```

The `prometheus/prometheus.yml` in the repository is pre-configured for
the Docker Compose observability profile.

## OpenTelemetry spans

When a tracer is configured, Aegis creates a root span per run with:

| Attribute | Value |
|---|---|
| `aegis.run_id` | UUID of the run |
| `aegis.route` | Route name |
| `aegis.principal` | Principal ID (redacted in logs) |
| `aegis.status` | Final run status |

Child spans are created for each pipeline node:

- `aegis.node.<name>` — span per guardrail or pipeline node
- `aegis.node.<name>.verdict` — verdict kind (allow/block/sanitize/require_approval)

## Configuring an exporter

```yaml title="aegis.yaml"
telemetry:
  exporter: otlp
  endpoint: http://otel-collector:4317
  service_name: aegis-gateway
```

Supported exporters: `otlp` (gRPC), `otlp_http`, `jaeger`, `zipkin`.
Custom exporters are plugin adapters implementing the telemetry exporter contract.

## Grafana

The repository ships a Grafana provisioning config at `grafana/provisioning/`.
Start the observability profile and open `http://localhost:3001`:

```bash
docker compose --profile observability up
```

The pre-built dashboard shows:

- Run rate and error rate by route
- P50/P95/P99 run duration
- Blocked vs completed run breakdown
- Active audit backlog

## Security note

`/metrics` is excluded from authentication middleware so Prometheus can
scrape without credentials. Restrict access at the network level (firewall,
nginx `allow`/`deny` directives) if the metrics endpoint is sensitive.
