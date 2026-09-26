# Metrics & traces

## Prometheus

`GET /metrics` — unauthenticated so Prometheus can scrape it; restrict it at
the network layer.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `aegis_runs_total` | counter | `route`, `status` | Runs finished, by final status. |
| `aegis_run_duration_seconds` | histogram | `route` | Wall-clock time per run. |
| `aegis_exporter_failures_total` | counter | `exporter` | Evidence records an [exporter](/guide/audit#forward-evidence-to-other-systems) failed to deliver. |

```yaml
scrape_configs:
  - job_name: aegis
    scrape_interval: 15s
    static_configs:
      - targets: ["aegis:8000"]
```

Useful queries:

```text
sum by (route) (rate(aegis_runs_total{status="blocked"}[5m]))          # blocks per second
histogram_quantile(0.95, sum by (le, route) (rate(aegis_run_duration_seconds_bucket[5m])))
sum(aegis_runs_total{status="paused"}) - sum(aegis_runs_total{status="denied"})  # rough review backlog
```

Point your own Prometheus at `/metrics` with the scrape config above;
Aegis doesn't bundle a monitoring stack.

## OpenTelemetry

Each run executes inside one span:

| Span | Attributes |
|---|---|
| `aegis.run` | `run.id`, `run.route`, `run.principal_id`, `run.status` |

Spans go to the process's global tracer provider (tracer name
`aegis.server`). Aegis doesn't install an exporter; either run under
auto-instrumentation —

```bash
pip install opentelemetry-distro opentelemetry-exporter-otlp
OTEL_SERVICE_NAME=aegis OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317 \
  opentelemetry-instrument aegis serve --config aegis.yaml
```

— or pass a `tracer=` to `create_app()` when embedding the server.

## Beyond metrics

The per-run event log (`aegis explain`, `GET /v1/runs/{id}`) and the
[evidence ledger](/guide/audit) carry the verdict-level detail that metrics
aggregate away.
