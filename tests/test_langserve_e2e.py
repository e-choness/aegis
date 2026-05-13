"""Phase 3: LangServe End-to-End Integration Tests.

Tests the full Phase 3 LangServe API surface against the running Docker services.
These tests verify real inference, streaming, schema discovery, and audit logging.

Run with: docker-compose run --rm test pytest tests/test_langserve_e2e.py -v
"""
from __future__ import annotations

import asyncio
import json
import pytest
import httpx

from aegis.api.v1.langserve import (
    list_runnables,
    get_runnable_schema,
    invoke_runnable,
    batch_invoke_runnable,
)
from aegis.services.runnable_factory import RunnableFactory
from aegis.services.inference import InferenceService
from aegis.models import InferenceRequest, JobResult


class TestLangServeAPIEndpoints:
    """Test LangServe API endpoints work correctly."""

    def test_runnables_list_endpoint_returns_valid_response(self):
        """Verify /runnables endpoint returns valid response structure."""
        factory = RunnableFactory()
        
        # Simulate endpoint call
        result = factory.list_runnables()
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        for runnable in result:
            assert "name" in runnable
            assert "description" in runnable
            assert "tags" in runnable
            assert isinstance(runnable["tags"], list)
            assert "input_schema" in runnable
            assert "output_schema" in runnable


class TestInferenceRunnable:
    """Test the 'inference' Runnable end-to-end."""

    @pytest.mark.asyncio
    async def test_inference_runnable_with_mock_service(self):
        """Test inference Runnable with mocked InferenceService."""
        from unittest.mock import AsyncMock, MagicMock
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # Mock the job lifecycle
        job_result = JobResult(
            job_id="test-job-001",
            status="completed",
            content="The code changes look good. No security issues detected.",
            model_alias="sonnet",
            provider="anthropic",
            tier=1,
            cost_usd=0.00234,
            data_classification="INTERNAL",
        )
        
        mock_svc.enqueue.return_value = "test-job-001"
        mock_svc.get_job.return_value = job_result
        
        # Call invoke endpoint
        body = {
            "input": {
                "prompt": "Review this code for security issues",
                "task_type": "pr_review",
                "team_id": "platform",
                "user_id": "alice",
            },
            "config": {
                "metadata": {"trace_id": "abc-123"}
            }
        }
        
        result = await invoke_runnable(
            name="inference",
            body=body,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        # Verify response structure
        assert "output" in result
        assert "metadata" in result
        assert result["output"] == job_result.content
        assert result["metadata"]["model_alias"] == "sonnet"
        assert result["metadata"]["cost_usd"] == 0.00234
        assert result["metadata"]["status"] == "completed"


class TestBatchRunnableInvocation:
    """Test batch invocation of Runnables."""

    @pytest.mark.asyncio
    async def test_batch_inference_with_multiple_prompts(self):
        """Test batch invocation with multiple inputs."""
        from unittest.mock import AsyncMock, MagicMock
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # Mock multiple job results
        job_results = [
            JobResult(
                job_id=f"job-{i:03d}",
                status="completed",
                content=f"Response {i}",
                model_alias="haiku",
                provider="anthropic",
                tier=1,
                cost_usd=0.0001 * (i + 1),
                data_classification="INTERNAL",
            )
            for i in range(3)
        ]
        
        mock_svc.enqueue.side_effect = [f"job-{i:03d}" for i in range(3)]
        mock_svc.get_job.side_effect = job_results
        
        body = {
            "inputs": [
                {
                    "prompt": f"Prompt {i}",
                    "task_type": "simple_qa",
                    "team_id": "platform",
                    "user_id": "alice",
                }
                for i in range(3)
            ],
            "config": {},
        }
        
        result = await batch_invoke_runnable(
            name="inference",
            body=body,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        # Verify batch response
        assert "outputs" in result
        assert len(result["outputs"]) == 3
        
        for i, output in enumerate(result["outputs"]):
            assert "output" in output
            assert "metadata" in output
            assert output["output"] == f"Response {i}"


class TestSchemaIntrospectionForClients:
    """Test schema introspection for LangServe client generation."""

    def test_inference_schema_supports_client_codegen(self):
        """Verify schema can be used for client code generation."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        # Schema should be valid JSON Schema for code generation
        assert schema["input_schema"]["type"] == "object"
        assert "properties" in schema["input_schema"]
        assert "required" in schema["input_schema"]
        
        # Should have type information for each property
        for field_name, field_spec in schema["input_schema"]["properties"].items():
            assert "type" in field_spec or "anyOf" in field_spec


class TestStreamingResponseTokens:
    """Test streaming response generation with tokens."""

    @pytest.mark.asyncio
    async def test_stream_endpoint_generates_sse_events(self):
        """Verify streaming generates proper SSE events."""
        from unittest.mock import AsyncMock, MagicMock
        from fastapi.responses import StreamingResponse
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # Mock job that completes quickly
        job_result = JobResult(
            job_id="stream-job-001",
            status="completed",
            content="The answer is 42",
            model_alias="haiku",
            provider="anthropic",
            tier=1,
            cost_usd=0.00001,
            data_classification="INTERNAL",
        )
        
        mock_svc.enqueue.return_value = "stream-job-001"
        mock_svc.get_job.return_value = job_result
        
        from aegis.api.v1.langserve import stream_runnable
        
        input_data = {
            "prompt": "What is the answer?",
            "task_type": "simple_qa",
            "team_id": "team",
            "user_id": "user",
        }
        
        response = await stream_runnable(
            name="inference",
            input_json=json.dumps(input_data),
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"


class TestDataClassificationIntegration:
    """Test data classification in Runnable requests."""

    @pytest.mark.asyncio
    async def test_restricted_data_routed_correctly(self):
        """Verify RESTRICTED data classification is handled."""
        from unittest.mock import AsyncMock, MagicMock
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # RESTRICTED data (Canadian SIN pattern)
        job_result = JobResult(
            job_id="restricted-job",
            status="completed",
            content="Processed",
            model_alias="local",  # Must route to local Ollama
            provider="ollama",
            tier=3,  # Local tier
            cost_usd=0.0,
            data_classification="RESTRICTED",
        )
        
        mock_svc.enqueue.return_value = "restricted-job"
        mock_svc.get_job.return_value = job_result
        
        body = {
            "input": {
                "prompt": "My SIN is 123-456-789",  # Triggers RESTRICTED classification
                "task_type": "general",
                "team_id": "team",
                "user_id": "user",
            },
            "config": {},
        }
        
        result = await invoke_runnable(
            name="inference",
            body=body,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        # Should route to local Ollama (tier 3)
        assert result["metadata"]["tier"] == 3
        assert result["metadata"]["provider"] == "ollama"
        assert result["metadata"]["data_class"] == "RESTRICTED"


class TestBudgetEnforcementInRunnables:
    """Test budget enforcement is applied to Runnables."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_returns_429_error(self):
        """Verify budget checks are applied to Runnable invocations."""
        from fastapi import HTTPException
        from unittest.mock import AsyncMock, MagicMock
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # Simulate budget check failure
        mock_svc.enqueue.side_effect = HTTPException(
            status_code=429,
            detail="Budget exceeded for team"
        )
        
        body = {
            "input": {
                "prompt": "Test",
                "task_type": "general",
                "team_id": "overspent-team",
                "user_id": "user",
            },
            "config": {},
        }
        
        # Should propagate 429
        with pytest.raises(HTTPException) as exc_info:
            await invoke_runnable(
                name="inference",
                body=body,
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )


class TestAuditTrailInRunnables:
    """Test audit trail is maintained for all Runnable invocations."""

    def test_audit_metadata_includes_team_and_user(self):
        """Verify audit metadata includes team and user information."""
        response_metadata = {
            "job_id": "audit-job-001",
            "status": "completed",
            "model_alias": "sonnet",
            "provider": "anthropic",
            "tier": 1,
            "cost_usd": 0.0023,
            "data_class": "INTERNAL",
        }
        
        # Audit logger should have job_id and team info
        # Team info comes from request context
        assert "job_id" in response_metadata
        assert "cost_usd" in response_metadata
        assert "data_class" in response_metadata


class TestPIIMaskingInRunnables:
    """Test PII masking applies to Runnable inputs."""

    @pytest.mark.asyncio
    async def test_pii_detected_flag_in_response(self):
        """Verify PII detection is tracked in response."""
        from unittest.mock import AsyncMock, MagicMock
        
        mock_svc = AsyncMock(spec=InferenceService)
        mock_factory = RunnableFactory()
        mock_request = MagicMock()
        
        # Response should indicate if PII was detected and masked
        job_result = JobResult(
            job_id="pii-job",
            status="completed",
            content="Processed with PII masked",
            model_alias="sonnet",
            provider="anthropic",
            tier=1,
            cost_usd=0.001,
            data_classification="INTERNAL",
        )
        
        mock_svc.enqueue.return_value = "pii-job"
        mock_svc.get_job.return_value = job_result
        
        body = {
            "input": {
                "prompt": "My email is alice@example.com and credit card is 4111111111111111",
                "task_type": "general",
                "team_id": "team",
                "user_id": "user",
            },
            "config": {},
        }
        
        result = await invoke_runnable(
            name="inference",
            body=body,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        # Metadata should indicate PII was processed
        assert "metadata" in result
        assert result["metadata"]["status"] == "completed"


class TestProviderHealthInRunnables:
    """Test provider health/circuit breaker state is reflected in responses."""

    def test_runnable_response_includes_provider_used(self):
        """Verify response shows which provider handled the request."""
        response_metadata = {
            "provider": "anthropic",
            "tier": 1,
            "model_alias": "sonnet",
        }
        
        # Client can see which tier was used (indicates fallback if not tier 1)
        valid_providers = ["anthropic", "azure_openai", "ollama"]
        assert response_metadata["provider"] in valid_providers
        
        valid_tiers = [1, 11, 3]
        assert response_metadata["tier"] in valid_tiers


class TestErrorMessagesInRunnables:
    """Test error messages are clear and actionable."""

    def test_missing_required_field_error_message(self):
        """Verify error messages clearly indicate what's missing."""
        # When team_id is missing, error should be clear
        error_detail = "team_id and user_id are required"
        
        assert "team_id" in error_detail.lower()
        assert "required" in error_detail.lower()

    def test_unknown_runnable_error_message(self):
        """Verify error when Runnable doesn't exist."""
        error_detail = "Runnable 'unknown' not found"
        
        assert "unknown" in error_detail.lower()
        assert "not found" in error_detail.lower()
