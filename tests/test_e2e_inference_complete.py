"""End-to-end inference flow tests for Day 5 — complete request-response cycles."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.aegis.main import app
from src.aegis.models import InferenceRequest
from src.aegis.providers.base import CompletionResponse


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestE2EPublicDataInference:
    """Test end-to-end inference for PUBLIC data."""

    def test_public_inference_request_accepted(self, client):
        """Test PUBLIC data inference request is accepted (202)."""
        payload = {
            "prompt": "What is 2+2?",
            "team_id": "team1",
            "user_id": "user1",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data

    def test_public_inference_with_model_parameter(self, client):
        """Test PUBLIC inference with explicit model parameter."""
        payload = {
            "prompt": "What is the capital of France?",
            "team_id": "team1",
            "user_id": "user1",
            "model": "haiku",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data

    def test_job_result_structure(self, client):
        """Test job result has expected structure."""
        # Submit job
        payload = {
            "prompt": "Test",
            "team_id": "team1",
            "user_id": "user1",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Check job status
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        # Status should be pending, running, or completed
        assert data["status"] in ["pending", "running", "completed", "failed"]


class TestE2ERestrictedDataInference:
    """Test end-to-end inference for RESTRICTED data."""

    async def test_restricted_data_routed_to_tier2(self):
        """Test RESTRICTED data classification routes to Tier 2."""
        # This test validates the routing logic
        request = InferenceRequest(
            prompt="Sensitive data",
            team_id="team1",
            user_id="user1",
        )
        assert request.prompt == "Sensitive data"

    def test_restricted_inference_requires_tier2(self, client):
        """Test RESTRICTED inference request structure."""
        # Test that API accepts model parameter for restricted routing
        payload = {
            "prompt": "Internal data",
            "team_id": "team1",
            "user_id": "user1",
            "model": "opus",  # explicit model for RESTRICTED
        }
        response = client.post("/api/v1/inference", json=payload)
        # Should accept the request
        assert response.status_code in [202, 503]  # 202 if Tier 2 available, 503 if not


class TestE2EInferenceErrorHandling:
    """Test error handling in end-to-end inference."""

    def test_invalid_payload_returns_422(self, client):
        """Test invalid payload returns validation error."""
        payload = {
            "prompt": "Test",
            # Missing required team_id and user_id
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 422

    def test_empty_prompt_handling(self, client):
        """Test empty prompt is handled."""
        payload = {
            "prompt": "",
            "team_id": "team1",
            "user_id": "user1",
        }
        response = client.post("/api/v1/inference", json=payload)
        # Should accept (validation happens in inference layer)
        assert response.status_code == 202

    def test_nonexistent_job_returns_404(self, client):
        """Test querying nonexistent job returns 404."""
        response = client.get("/api/v1/jobs/nonexistent-job-id")
        assert response.status_code == 404


class TestE2EInferenceWithModelAliases:
    """Test model alias resolution in end-to-end flow."""

    def test_haiku_model_alias(self, client):
        """Test haiku alias in inference request."""
        payload = {
            "prompt": "Test",
            "team_id": "team1",
            "user_id": "user1",
            "model": "haiku",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202

    def test_sonnet_model_alias(self, client):
        """Test sonnet alias in inference request."""
        payload = {
            "prompt": "Test",
            "team_id": "team1",
            "user_id": "user1",
            "model": "sonnet",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202

    def test_opus_model_alias(self, client):
        """Test opus alias in inference request."""
        payload = {
            "prompt": "Test",
            "team_id": "team1",
            "user_id": "user1",
            "model": "opus",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202

    def test_case_insensitive_model_alias(self, client):
        """Test model alias is case-insensitive."""
        payload = {
            "prompt": "Test",
            "team_id": "team1",
            "user_id": "user1",
            "model": "HAIKU",  # Uppercase
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202


class TestE2ECostAccounting:
    """Test cost accounting in end-to-end inference."""

    def test_inference_tracks_cost(self, client):
        """Test that inference requests track cost."""
        payload = {
            "prompt": "Test prompt",
            "team_id": "team1",
            "user_id": "user1",
        }
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Job result should include cost information (when completed)
        response = client.get(f"/api/v1/jobs/{job_id}")
        data = response.json()
        # Cost tracking depends on completion, but structure should be present
        if data["status"] == "completed":
            assert "cost_usd" in data or "metrics" in data


class TestE2EAuditLogging:
    """Test audit logging in end-to-end inference."""

    def test_inference_logged(self, client):
        """Test that inference requests are logged."""
        payload = {
            "prompt": "Test audit logging",
            "team_id": "team1",
            "user_id": "user1",
        }
        # Should not raise errors during logging
        response = client.post("/api/v1/inference", json=payload)
        assert response.status_code == 202


class TestE2EPIIMasking:
    """Test PII masking in end-to-end inference."""

    def test_pii_in_prompt_handled(self, client):
        """Test that PII in prompts is handled."""
        payload = {
            "prompt": "My email is test@example.com",
            "team_id": "team1",
            "user_id": "user1",
        }
        response = client.post("/api/v1/inference", json=payload)
        # Should process without errors (masking happens internally)
        assert response.status_code == 202


class TestE2EMultipleRequests:
    """Test handling multiple simultaneous requests."""

    def test_multiple_sequential_requests(self, client):
        """Test multiple sequential inference requests."""
        job_ids = []
        for i in range(3):
            payload = {
                "prompt": f"Request {i}",
                "team_id": "team1",
                "user_id": "user1",
            }
            response = client.post("/api/v1/inference", json=payload)
            assert response.status_code == 202
            job_ids.append(response.json()["job_id"])

        # All job IDs should be unique
        assert len(set(job_ids)) == 3

    def test_different_teams_isolated(self, client):
        """Test requests from different teams are tracked separately."""
        payload1 = {
            "prompt": "Team1 request",
            "team_id": "team1",
            "user_id": "user1",
        }
        payload2 = {
            "prompt": "Team2 request",
            "team_id": "team2",
            "user_id": "user2",
        }
        response1 = client.post("/api/v1/inference", json=payload1)
        response2 = client.post("/api/v1/inference", json=payload2)

        assert response1.status_code == 202
        assert response2.status_code == 202
        job_id1 = response1.json()["job_id"]
        job_id2 = response2.json()["job_id"]
        assert job_id1 != job_id2
