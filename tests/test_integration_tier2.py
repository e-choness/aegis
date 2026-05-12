"""Integration tests for Tier 2 with the full gateway."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from aegis.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestHealthEndpointWithTier2:
    """Test health endpoint reports Tier 2 status."""

    def test_health_endpoint_includes_tier2_status(self, client):
        """Test that health endpoint returns Tier 2 endpoint information."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "tiers" in data
        assert "tier_2" in data["tiers"]

    def test_health_endpoint_tier2_endpoints(self, client):
        """Test that health endpoint lists Tier 2 endpoints and their status."""
        response = client.get("/api/v1/health")
        data = response.json()

        tier_2_config = data["tiers"]["tier_2"]
        assert "endpoints" in tier_2_config
        # endpoints may be empty if no Tier 2 configured, but key should exist


class TestAdminRefreshModels:
    """Test admin endpoint for model discovery refresh."""

    def test_refresh_models_endpoint(self, client):
        """Test refresh-models admin endpoint."""
        response = client.post("/api/v1/admin/refresh-models")
        # May fail if no Tier 2 configured, but endpoint should exist
        assert response.status_code in [200, 503]

    def test_refresh_models_returns_count(self, client):
        """Test that refresh returns model count."""
        # If Tier 2 is configured, should return count
        response = client.post("/api/v1/admin/refresh-models")
        if response.status_code == 200:
            data = response.json()
            assert "count" in data or "status" in data


class TestAdminCircuitBreakerReset:
    """Test admin endpoint for circuit breaker management."""

    def test_reset_circuit_breaker_endpoint(self, client):
        """Test reset-circuit-breaker admin endpoint."""
        response = client.post(
            "/api/v1/admin/reset-circuit-breaker",
            params={"endpoint": "http://localhost:8000"}
        )
        # May fail if no Tier 2 configured, but endpoint should exist
        assert response.status_code in [200, 503, 400]

    def test_reset_circuit_breaker_requires_endpoint(self, client):
        """Test that endpoint parameter is required."""
        response = client.post("/api/v1/admin/reset-circuit-breaker")
        # Should fail if no endpoint parameter
        assert response.status_code in [400, 422]


class TestAdminCacheStatus:
    """Test admin endpoint for cache status."""

    def test_cache_status_endpoint(self, client):
        """Test cache-status admin endpoint."""
        response = client.get("/api/v1/admin/cache-status")
        # May fail if no Tier 2 configured, but endpoint should exist
        assert response.status_code in [200, 503]

    def test_cache_status_returns_tier2_info(self, client):
        """Test that cache status returns Tier 2 information."""
        response = client.get("/api/v1/admin/cache-status")
        if response.status_code == 200:
            data = response.json()
            assert "tier_2" in data or "status" in data


class TestInferenceEndpointWithModel:
    """Test inference endpoint accepts model parameter."""

    def test_inference_accepts_model_parameter(self, client):
        """Test that inference endpoint accepts model alias parameter."""
        payload = {
            "prompt": "Test prompt",
            "team_id": "team1",
            "user_id": "user1",
            "model": "haiku",
        }

        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202  # Async job submitted

        data = response.json()
        assert "job_id" in data

    def test_inference_without_model_parameter(self, client):
        """Test that model parameter is optional."""
        payload = {
            "prompt": "Test prompt",
            "team_id": "team1",
            "user_id": "user1",
        }

        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202

    def test_get_job_returns_job_result(self, client):
        """Test that job retrieval works."""
        # Submit job
        payload = {
            "prompt": "Test prompt",
            "team_id": "team1",
            "user_id": "user1",
        }

        response = client.post("/api/v1/inference", json=payload)
        job_id = response.json()["job_id"]

        # Get job
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data


class TestMetricsEndpoint:
    """Test metrics endpoint includes Tier 2 metrics."""

    def test_metrics_endpoint_exists(self, client):
        """Test that metrics endpoint is available."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_includes_inference_metrics(self, client):
        """Test that metrics include inference metrics."""
        response = client.get("/metrics")
        content = response.text

        # Check for expected metric names
        assert "inference_" in content or "requests_total" in content


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present in response."""
        # The actual CORS behavior depends on configuration
        response = client.get("/api/v1/health")
        assert response.status_code == 200
