"""Phase 3: LangServe Runnables — Unit and Integration Tests.

All tests run inside Docker (no local Python/dependencies required).
Execute with: docker-compose run --rm test pytest tests/test_langserve_runnables.py -v
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aegis.api.v1.langserve import (
    list_runnables,
    get_runnable_schema,
    invoke_runnable,
    batch_invoke_runnable,
    stream_runnable,
)
from aegis.services.runnable_factory import (
    RunnableFactory,
    InferenceInput,
    InferenceOutput,
)
from aegis.models import InferenceRequest, JobResult


class TestRunnableFactory:
    """Test the RunnableFactory service."""

    def test_factory_initializes_with_builtin_runnables(self):
        """Verify built-in Runnables are registered on initialization."""
        factory = RunnableFactory()
        runnables = factory.list_runnables()
        
        assert len(runnables) >= 1
        names = [r["name"] for r in runnables]
        assert "inference" in names

    def test_inference_runnable_has_valid_schemas(self):
        """Verify the 'inference' Runnable has input and output schemas."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        
        assert schema is not None
        assert "input_schema" in schema
        assert "output_schema" in schema
        assert schema["name"] == "inference"
        assert "inference" in schema["tags"]

    def test_inference_input_schema_has_required_fields(self):
        """Verify input schema requires prompt, task_type, team_id, user_id."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        input_schema = schema["input_schema"]
        
        assert "prompt" in input_schema.get("properties", {})
        assert "task_type" in input_schema.get("properties", {})
        assert "team_id" in input_schema.get("properties", {})
        assert "user_id" in input_schema.get("properties", {})
        
        # Check required fields
        required = input_schema.get("required", [])
        assert "prompt" in required
        assert "team_id" in required
        assert "user_id" in required

    def test_inference_output_schema_has_output_and_metadata(self):
        """Verify output schema includes output and metadata fields."""
        factory = RunnableFactory()
        schema = factory.get_schema("inference")
        output_schema = schema["output_schema"]
        
        assert "output" in output_schema.get("properties", {})
        assert "metadata" in output_schema.get("properties", {})

    def test_list_runnables_returns_all_metadata(self):
        """Verify list_runnables returns complete metadata."""
        factory = RunnableFactory()
        runnables = factory.list_runnables()
        
        assert isinstance(runnables, list)
        for runnable in runnables:
            assert "name" in runnable
            assert "description" in runnable
            assert "tags" in runnable
            assert "input_schema" in runnable
            assert "output_schema" in runnable

    def test_has_runnable_checks_registration(self):
        """Verify has_runnable correctly identifies registered Runnables."""
        factory = RunnableFactory()
        
        assert factory.has_runnable("inference") is True
        assert factory.has_runnable("nonexistent") is False

    def test_get_schema_returns_none_for_missing_runnable(self):
        """Verify get_schema returns None for unregistered Runnables."""
        factory = RunnableFactory()
        
        assert factory.get_schema("nonexistent") is None

    def test_register_custom_runnable_adds_to_registry(self):
        """Verify custom Runnables can be registered."""
        factory = RunnableFactory()
        
        custom_input = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }
        custom_output = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
        }
        
        factory.register_custom_runnable(
            name="custom_transform",
            description="Custom text transformation",
            tags=["custom", "text"],
            input_schema=custom_input,
            output_schema=custom_output,
        )
        
        assert factory.has_runnable("custom_transform") is True
        schema = factory.get_schema("custom_transform")
        assert schema["name"] == "custom_transform"
        assert schema["description"] == "Custom text transformation"


class TestInferenceInputSchema:
    """Test the InferenceInput Pydantic model."""

    def test_inference_input_validates_required_fields(self):
        """Verify InferenceInput requires prompt, team_id, user_id."""
        # Should pass with required fields
        inp = InferenceInput(
            prompt="Test prompt",
            team_id="test-team",
            user_id="test-user",
        )
        assert inp.prompt == "Test prompt"
        assert inp.team_id == "test-team"
        assert inp.user_id == "test-user"

    def test_inference_input_has_defaults(self):
        """Verify InferenceInput has sensible defaults."""
        inp = InferenceInput(
            prompt="Test",
            team_id="team",
            user_id="user",
        )
        assert inp.task_type == "general"
        assert inp.complexity == "medium"
        assert inp.trace_id is None

    def test_inference_input_json_schema_generation(self):
        """Verify Pydantic can generate JSON schema."""
        schema = InferenceInput.model_json_schema()
        
        assert "properties" in schema
        assert "prompt" in schema["properties"]
        assert "required" in schema
        assert "prompt" in schema["required"]
        assert "team_id" in schema["required"]
        assert "user_id" in schema["required"]


class TestInferenceOutputSchema:
    """Test the InferenceOutput Pydantic model."""

    def test_inference_output_structure(self):
        """Verify InferenceOutput can hold output and metadata."""
        output = InferenceOutput(
            output="Test response",
            metadata={
                "model_alias": "sonnet",
                "provider": "anthropic",
                "cost_usd": 0.0023,
            }
        )
        assert output.output == "Test response"
        assert output.metadata["model_alias"] == "sonnet"

    def test_inference_output_json_schema_generation(self):
        """Verify InferenceOutput generates valid JSON schema."""
        schema = InferenceOutput.model_json_schema()
        
        assert "properties" in schema
        assert "output" in schema["properties"]
        assert "metadata" in schema["properties"]


class TestListRunnablesEndpoint:
    """Test the GET /runnables endpoint."""

    @pytest.mark.asyncio
    async def test_list_runnables_returns_runnables(self):
        """Verify /runnables endpoint returns runnable list."""
        # Mock the request and factory
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_request.app.state.runnable_factory = mock_factory
        
        # Call endpoint with dependency injection
        result = await list_runnables(factory=mock_factory)
        
        assert "runnables" in result
        assert len(result["runnables"]) >= 1
        assert any(r["name"] == "inference" for r in result["runnables"])


class TestSchemaEndpoint:
    """Test the GET /runnables/{name}/schema endpoint."""

    @pytest.mark.asyncio
    async def test_get_schema_returns_valid_schema(self):
        """Verify /schema endpoint returns Runnable schema."""
        mock_factory = RunnableFactory()
        
        result = await get_runnable_schema(name="inference", factory=mock_factory)
        
        assert result is not None
        assert result["name"] == "inference"
        assert "input_schema" in result
        assert "output_schema" in result

    @pytest.mark.asyncio
    async def test_get_schema_returns_404_for_missing_runnable(self):
        """Verify /schema returns 404 for unknown Runnable."""
        from fastapi import HTTPException
        
        mock_factory = RunnableFactory()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_runnable_schema(name="nonexistent", factory=mock_factory)
        
        assert exc_info.value.status_code == 404


class TestInvokeEndpoint:
    """Test the POST /runnables/{name}/invoke endpoint."""

    @pytest.mark.asyncio
    async def test_invoke_inference_with_valid_input(self):
        """Verify /invoke processes valid inference requests."""
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        # Mock the inference service response
        job_result = JobResult(
            job_id="test-job-123",
            status="completed",
            content="Test response",
            model_alias="sonnet",
            provider="anthropic",
            tier=1,
            cost_usd=0.0023,
            data_classification="INTERNAL",
        )
        mock_svc.enqueue.return_value = "test-job-123"
        mock_svc.get_job.return_value = job_result
        
        body = {
            "input": {
                "prompt": "Test prompt",
                "task_type": "simple_qa",
                "team_id": "test-team",
                "user_id": "test-user",
            },
            "config": {"metadata": {"trace_id": "trace-123"}},
        }
        
        result = await invoke_runnable(
            name="inference",
            body=body,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        assert "output" in result
        assert "metadata" in result
        assert result["output"] == "Test response"
        assert result["metadata"]["model_alias"] == "sonnet"

    @pytest.mark.asyncio
    async def test_invoke_returns_404_for_missing_runnable(self):
        """Verify /invoke returns 404 for unknown Runnable."""
        from fastapi import HTTPException
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        body = {"input": {}, "config": {}}
        
        with pytest.raises(HTTPException) as exc_info:
            await invoke_runnable(
                name="nonexistent",
                body=body,
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invoke_returns_400_for_missing_team_id(self):
        """Verify /invoke returns 400 when team_id is missing."""
        from fastapi import HTTPException
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        body = {
            "input": {
                "prompt": "Test",
                "task_type": "simple_qa",
                "team_id": "",  # Missing
                "user_id": "user",
            },
            "config": {},
        }
        
        with pytest.raises(HTTPException) as exc_info:
            await invoke_runnable(
                name="inference",
                body=body,
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )
        
        assert exc_info.value.status_code == 400


class TestBatchEndpoint:
    """Test the POST /runnables/{name}/batch endpoint."""

    @pytest.mark.asyncio
    async def test_batch_invoke_processes_multiple_inputs(self):
        """Verify /batch processes multiple inputs."""
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        job_result = JobResult(
            job_id="test-job",
            status="completed",
            content="Response",
            model_alias="sonnet",
            provider="anthropic",
            tier=1,
            cost_usd=0.001,
            data_classification="INTERNAL",
        )
        mock_svc.enqueue.return_value = "test-job"
        mock_svc.get_job.return_value = job_result
        
        body = {
            "inputs": [
                {"prompt": "Prompt 1", "task_type": "simple_qa", "team_id": "team", "user_id": "user"},
                {"prompt": "Prompt 2", "task_type": "simple_qa", "team_id": "team", "user_id": "user"},
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
        
        assert "outputs" in result
        assert len(result["outputs"]) == 2
        assert all("output" in output for output in result["outputs"])

    @pytest.mark.asyncio
    async def test_batch_returns_400_for_empty_inputs(self):
        """Verify /batch returns 400 when inputs is empty."""
        from fastapi import HTTPException
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        body = {"inputs": [], "config": {}}
        
        with pytest.raises(HTTPException) as exc_info:
            await batch_invoke_runnable(
                name="inference",
                body=body,
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )
        
        assert exc_info.value.status_code == 400


class TestStreamEndpoint:
    """Test the GET /runnables/{name}/stream endpoint."""

    @pytest.mark.asyncio
    async def test_stream_returns_streaming_response(self):
        """Verify /stream returns a streaming response."""
        from fastapi.responses import StreamingResponse
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        job_result = JobResult(
            job_id="test-job",
            status="completed",
            content="Test response",
            model_alias="sonnet",
            provider="anthropic",
            tier=1,
            cost_usd=0.001,
            data_classification="INTERNAL",
        )
        mock_svc.get_job.return_value = job_result
        mock_svc.enqueue.return_value = "test-job"
        
        input_data = {
            "prompt": "Test",
            "task_type": "simple_qa",
            "team_id": "team",
            "user_id": "user",
        }
        input_json = json.dumps(input_data)
        
        result = await stream_runnable(
            name="inference",
            input_json=input_json,
            request=mock_request,
            svc=mock_svc,
            factory=mock_factory,
        )
        
        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_stream_returns_400_for_missing_input_json(self):
        """Verify /stream returns 400 when input_json is missing."""
        from fastapi import HTTPException
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await stream_runnable(
                name="inference",
                input_json=None,
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )
        
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stream_returns_400_for_invalid_json(self):
        """Verify /stream returns 400 for invalid JSON."""
        from fastapi import HTTPException
        
        mock_request = MagicMock()
        mock_factory = RunnableFactory()
        mock_svc = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await stream_runnable(
                name="inference",
                input_json="not valid json {",
                request=mock_request,
                svc=mock_svc,
                factory=mock_factory,
            )
        
        assert exc_info.value.status_code == 400
