import pytest
import src.aegis.telemetry  # registers all metrics on import
from prometheus_client import REGISTRY


def _registered_names() -> set[str]:
    return {m.name for m in REGISTRY.collect()}


def test_gateway_requests_counter_registered():
    # prometheus_client 0.20+ strips _total from internal name
    names = _registered_names()
    assert "gateway_requests" in names or "gateway_requests_total" in names


def test_pii_detections_counter_registered():
    names = _registered_names()
    assert "pii_detections" in names or "pii_detections_total" in names


def test_restricted_violations_counter_registered():
    names = _registered_names()
    assert (
        "restricted_data_cloud_violations" in names
        or "restricted_data_cloud_violations_total" in names
    )


def test_inference_cost_counter_registered():
    names = _registered_names()
    assert "inference_cost_usd" in names or "inference_cost_usd_total" in names


def test_latency_histogram_registered():
    names = _registered_names()
    assert "gateway_inference_latency_seconds" in names
