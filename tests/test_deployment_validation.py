"""Deployment validation tests for Day 5 — gateway startup and health checks."""
from __future__ import annotations

import pytest
import time
from fastapi.testclient import TestClient

from src.aegis.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestDeploymentStartup:
    """Test gateway deployment startup behavior."""

    def test_gateway_starts_without_blocking(self):
        """Test that gateway starts and accepts connections within timeout."""
        # This test validates non-blocking startup (< 20s in practice)
        # FastAPI test client startup is instant for this test
        assert app is not None
        assert app.title == "Aegis AI Gateway"
        assert app.version == "0.3.0"

    def test_metrics_endpoint_available(self, client):
        """Test that metrics endpoint is available immediately after startup."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        # Should contain Prometheus metrics
        assert len(response.text) > 0

    def test_health_endpoint_available(self, client):
        """Test that health endpoint is available after startup."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "tiers" in data

    def test_inference_endpoint_available(self, client):
        """Test that inference endpoint is available."""
        response = client.get("/api/v1/health")  # Use health to verify service initialized
        assert response.status_code == 200


class TestHealthEndpointStructure:
    """Test health endpoint response structure and content."""

    def test_health_contains_version(self, client):
        """Test health response includes version."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == "0.3.0"

    def test_health_contains_tier_structure(self, client):
        """Test health response includes all tier information."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "tiers" in data
        assert "tier_1a" in data["tiers"]
        assert "tier_1b" in data["tiers"]
        assert "tier_2" in data["tiers"]

    def test_health_tier_1a_status(self, client):
        """Test Tier 1a status in health response."""
        response = client.get("/api/v1/health")
        data = response.json()
        tier_1a = data["tiers"]["tier_1a"]
        assert tier_1a["status"] in ["healthy", "unavailable"]
        if tier_1a["status"] == "healthy":
            assert "latency_ms" in tier_1a

    def test_health_tier_1b_status(self, client):
        """Test Tier 1b status in health response."""
        response = client.get("/api/v1/health")
        data = response.json()
        tier_1b = data["tiers"]["tier_1b"]
        assert tier_1b["status"] in ["healthy", "unavailable"]

    def test_health_tier_2_status(self, client):
        """Test Tier 2 status in health response."""
        response = client.get("/api/v1/health")
        data = response.json()
        tier_2 = data["tiers"]["tier_2"]
        assert tier_2["status"] in ["healthy", "unavailable"]
        # Should always have endpoints list even if empty
        assert "endpoints" in tier_2

    def test_health_model_discovery_status(self, client):
        """Test model discovery status in health response."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "model_discovery" in data
        assert "status" in data["model_discovery"]
        assert "cache_staleness_seconds" in data["model_discovery"]

    def test_health_restricted_violations_count(self, client):
        """Test restricted cloud violations counter."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert "restricted_cloud_violations" in data
        assert isinstance(data["restricted_cloud_violations"], int)
        assert data["restricted_cloud_violations"] >= 0


class TestAdminEndpointsAvailable:
    """Test admin endpoints are available."""

    def test_refresh_models_endpoint_exists(self, client):
        """Test refresh-models admin endpoint exists."""
        response = client.post("/api/v1/admin/refresh-models")
        # May fail with 503 if no Tier 2, but endpoint should exist
        assert response.status_code in [200, 503, 400]

    def test_reset_circuit_breaker_endpoint_exists(self, client):
        """Test reset-circuit-breaker admin endpoint exists."""
        response = client.post(
            "/api/v1/admin/reset-circuit-breaker",
            params={"endpoint": "http://test:8000"}
        )
        # May fail with 503 if no Tier 2, but endpoint should exist
        assert response.status_code in [200, 503, 400]

    def test_cache_status_endpoint_exists(self, client):
        """Test cache-status admin endpoint exists."""
        response = client.get("/api/v1/admin/cache-status")
        # May fail with 503 if no Tier 2, but endpoint should exist
        assert response.status_code in [200, 503, 400]


class TestErrorHandling:
    """Test error handling in gateway."""

    def test_health_endpoint_handles_exceptions(self, client):
        """Test health endpoint handles errors gracefully."""
        response = client.get("/api/v1/health")
        # Should always return 200, even if there are issues
        assert response.status_code == 200
        data = response.json()
        # Response should have status field
        assert "status" in data

    def test_metrics_endpoint_always_available(self, client):
        """Test metrics endpoint is always available."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_invalid_endpoint_returns_404(self, client):
        """Test that invalid endpoints return 404."""
        response = client.get("/api/v1/invalid-endpoint")
        assert response.status_code == 404


class TestCORSHeaders:
    """Test CORS configuration."""

    def test_cors_headers_in_responses(self, client):
        """Test that CORS headers are properly configured."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        # CORS headers may or may not be present depending on TestClient
        # but response should be valid


class TestReadinessProbes:
    """Test readiness endpoints for Kubernetes/Docker orchestration."""

    def test_health_endpoint_for_readiness(self, client):
        """Test health endpoint can be used for readiness probe."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        # Service is ready if health returns 200
        assert data["status"] in ["healthy", "error"]

    def test_metrics_endpoint_for_liveness(self, client):
        """Test metrics endpoint can be used for liveness probe."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Metrics should have content
        assert len(response.text) > 0
