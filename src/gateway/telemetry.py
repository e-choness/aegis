from __future__ import annotations
from prometheus_client import Counter, Histogram, Gauge

requests_total = Counter(
    "gateway_requests_total",
    "Total inference requests processed",
    ["team_id", "model_alias", "provider", "tier", "status"],
)

inference_cost_usd_total = Counter(
    "inference_cost_usd_total",
    "Cumulative inference cost in USD",
    ["team_id", "model_alias", "provider", "tier"],
)

pii_detections_total = Counter(
    "pii_detections_total",
    "PII entity detections in prompts",
    ["entity_type"],
)

restricted_cloud_violations_total = Counter(
    "restricted_data_cloud_violations_total",
    "RESTRICTED data routed to cloud providers — must always be 0",
)

inference_latency_seconds = Histogram(
    "gateway_inference_latency_seconds",
    "End-to-end inference latency",
    ["model_alias", "provider"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

provider_health_up = Gauge(
    "provider_health_up",
    "Provider health status (1=up, 0=down)",
    ["provider", "tier"],
)

budget_utilization_ratio = Gauge(
    "budget_utilization_ratio",
    "Team budget utilization 0.0–1.0",
    ["team_id"],
)
