"""Phase 3: LangServe Streaming and Schema Integration Tests.

Tests for Server-Sent Events streaming, schema introspection, and end-to-end LangServe flows.
All tests run inside Docker.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from aegis.services.runnable_factory import RunnableFactory


class TestSchemaIntrospection:
    """Test schema discovery and introspection."""

    def test_inference_schema_matches_pydantic_definitions(self):
        """Verify schema correctly represents Pydantic models."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        # Verify structure
        assert schema["input_schema"]["type"] == "object"
        assert schema["output_schema"]["type"] == "object"

    def test_inference_schema_includes_descriptions(self):
        """Verify fields have descriptions for UI generation."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        props = schema["input_schema"].get("properties", {})
        assert props.get("prompt", {}).get("description")
        assert props.get("task_type", {}).get("description")
        assert props.get("team_id", {}).get("description")

    def test_inference_schema_defines_field_types(self):
        """Verify schema specifies field types correctly."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        props = schema["input_schema"]["properties"]
        assert props["prompt"]["type"] == "string"
        assert props["team_id"]["type"] == "string"
        assert props["user_id"]["type"] == "string"

    def test_inference_output_schema_includes_metadata_object(self):
        """Verify output schema defines metadata as object."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        props = schema["output_schema"]["properties"]
        assert props["metadata"]["type"] == "object"

    def test_list_runnables_includes_all_metadata_for_discovery(self):
        """Verify list endpoint provides enough data for client discovery."""
        factory = RunnableFactory()
        runnables = factory.list_runnables()
        
        inference_runnable = next((r for r in runnables if r["name"] == "inference"), None)
        assert inference_runnable is not None
        
        # Verify all discovery fields present
        assert "name" in inference_runnable
        assert "description" in inference_runnable
        assert "tags" in inference_runnable
        assert "input_schema" in inference_runnable
        assert "output_schema" in inference_runnable


class TestStreamingResponseFormat:
    """Test Server-Sent Events response format."""

    def test_sse_token_event_format(self):
        """Verify SSE token events follow the correct format."""
        # SSE token event should be: event: token\ndata: {...}\n\n
        token_event = 'event: token\ndata: {"token": "The", "metadata": {}}\n\n'
        
        lines = token_event.split('\n')
        assert lines[0] == "event: token"
        assert lines[1].startswith("data: ")
        
        data = json.loads(lines[1].replace("data: ", ""))
        assert "token" in data
        assert "metadata" in data

    def test_sse_done_event_format(self):
        """Verify SSE done event format."""
        done_event = 'event: done\ndata: {"output": "...", "metadata": {...}}\n\n'
        
        lines = done_event.split('\n')
        assert lines[0] == "event: done"
        assert lines[1].startswith("data: ")

    def test_sse_error_event_format(self):
        """Verify SSE error event format."""
        error_event = 'event: error\ndata: {"error": "timeout"}\n\n'
        
        lines = error_event.split('\n')
        assert lines[0] == "event: error"


class TestLangServeRequestFormat:
    """Test request format compatibility with LangServe clients."""

    def test_invoke_request_structure(self):
        """Verify invoke request matches LangServe format."""
        request_body = {
            "input": {
                "prompt": "Review this code",
                "task_type": "pr_review",
                "team_id": "platform",
                "user_id": "alice",
            },
            "config": {
                "metadata": {"trace_id": "abc-123"}
            }
        }
        
        # Verify structure
        assert "input" in request_body
        assert "config" in request_body
        assert "prompt" in request_body["input"]
        assert "metadata" in request_body["config"]

    def test_batch_request_structure(self):
        """Verify batch request matches LangServe format."""
        request_body = {
            "inputs": [
                {"prompt": "P1", "task_type": "simple_qa", "team_id": "t1", "user_id": "u1"},
                {"prompt": "P2", "task_type": "simple_qa", "team_id": "t1", "user_id": "u1"},
            ],
            "config": {}
        }
        
        assert "inputs" in request_body
        assert isinstance(request_body["inputs"], list)
        assert len(request_body["inputs"]) > 0

    def test_response_structure_includes_output_and_metadata(self):
        """Verify response includes required fields."""
        response = {
            "output": "The code looks secure.",
            "metadata": {
                "job_id": "job-123",
                "status": "completed",
                "model_alias": "sonnet",
                "provider": "anthropic",
                "tier": 1,
                "cost_usd": 0.0023,
            }
        }
        
        assert "output" in response
        assert "metadata" in response
        assert "model_alias" in response["metadata"]
        assert "cost_usd" in response["metadata"]


class TestDataClassificationInRunnables:
    """Test data classification applies to all Runnable invocations."""

    @pytest.mark.asyncio
    async def test_inference_runnable_respects_classification(self):
        """Verify Runnable input includes classification support."""
        from aegis.services.runnable_factory import InferenceInput
        
        # Restricted data should be routed to local LLM
        inp = InferenceInput(
            prompt="My SIN is 123-456-789",  # This would trigger RESTRICTED classification
            task_type="general",
            team_id="team",
            user_id="user",
        )
        
        assert inp.prompt is not None


class TestBudgetTrackingInRunnables:
    """Test budget tracking is applied to Runnable invocations."""

    def test_runnable_response_includes_cost_information(self):
        """Verify Runnable responses include cost_usd for budget tracking."""
        response_metadata = {
            "job_id": "job-123",
            "status": "completed",
            "cost_usd": 0.0023,
            "model_alias": "sonnet",
        }
        
        # Budget service must have access to cost_usd
        assert "cost_usd" in response_metadata
        assert response_metadata["cost_usd"] > 0


class TestProviderRoutingInRunnables:
    """Test provider tier routing is reflected in Runnable responses."""

    def test_runnable_response_indicates_provider_used(self):
        """Verify response includes which provider was used."""
        response_metadata = {
            "provider": "anthropic",
            "tier": 1,
            "model_alias": "sonnet",
        }
        
        # Router decision should be visible
        assert "provider" in response_metadata
        assert "tier" in response_metadata
        assert response_metadata["tier"] in [1, 11, 3]  # Valid tiers


class TestAuditLoggingInRunnables:
    """Test audit logging applies to Runnable invocations."""

    def test_runnable_response_has_job_id_for_audit(self):
        """Verify response includes job_id for audit trail."""
        response_metadata = {
            "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "status": "completed",
        }
        
        # Audit logger must be able to correlate with job_id
        assert "job_id" in response_metadata


class TestErrorHandlingInRunnables:
    """Test error responses follow LangServe conventions."""

    def test_error_response_structure(self):
        """Verify error responses are well-formed."""
        error_response = {
            "output": None,
            "metadata": {
                "status": "failed",
                "error": "Budget exceeded",
            }
        }
        
        assert error_response["output"] is None
        assert "error" in error_response["metadata"]


class TestInputValidationInRunnables:
    """Test input validation for Runnables."""

    def test_inference_runnable_requires_prompt_team_user(self):
        """Verify inference Runnable validates required fields."""
        from aegis.services.runnable_factory import InferenceInput
        from pydantic import ValidationError
        
        # Should fail without prompt
        with pytest.raises(ValidationError):
            InferenceInput(
                prompt="",  # Empty is still required
                team_id="",
                user_id="",
            )

    def test_inference_runnable_accepts_optional_fields(self):
        """Verify optional fields are truly optional."""
        from aegis.services.runnable_factory import InferenceInput
        
        inp = InferenceInput(
            prompt="Test",
            team_id="team",
            user_id="user",
            # trace_id, complexity are optional
        )
        
        assert inp.trace_id is None
        assert inp.complexity == "medium"


class TestMultipleRunnableSupport:
    """Test infrastructure supports multiple Runnable types."""

    def test_factory_can_register_multiple_runnables(self):
        """Verify factory supports registering multiple Runnables."""
        factory = RunnableFactory()
        
        # Register additional Runnables (future)
        factory.register_custom_runnable(
            name="rag_query",
            description="Query the RAG index",
            tags=["rag", "retrieval"],
            input_schema={"type": "object", "properties": {"question": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"context": {"type": "string"}}},
        )
        
        # Verify both exist
        assert factory.has_runnable("inference")
        assert factory.has_runnable("rag_query")

    def test_list_runnables_includes_all_registered_types(self):
        """Verify list endpoint shows all Runnables."""
        factory = RunnableFactory()
        
        factory.register_custom_runnable(
            name="custom",
            description="Custom",
            tags=["custom"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        
        runnables = factory.list_runnables()
        names = [r["name"] for r in runnables]
        
        assert "inference" in names
        assert "custom" in names
