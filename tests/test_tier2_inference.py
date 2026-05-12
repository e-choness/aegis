"""Tests for Tier 2 external LLM provider integration with InferenceService."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.aegis.models import InferenceRequest, JobResult
from src.aegis.services.inference import InferenceService
from src.aegis.services.health import ProviderHealth
from src.aegis.services.budget import BudgetService
from src.aegis.services.audit import AuditLogger
from src.aegis.services.pii import PIIMasker
from src.aegis.services.model_lifecycle import ModelLifecycleManager
from src.aegis.providers.base import CompletionResponse


class TestModelAliasResolution:
    """Test model alias resolution for Tier 2."""

    def test_resolve_model_alias_haiku(self):
        """Test resolving haiku alias to actual model ID."""
        aliases = {"haiku": "neural-chat-7b"}
        service = InferenceService(model_aliases=aliases)

        model_id = service._resolve_model_alias("haiku")
        assert model_id == "neural-chat-7b"

    def test_resolve_model_alias_sonnet(self):
        """Test resolving sonnet alias."""
        aliases = {"sonnet": "mistral-7b"}
        service = InferenceService(model_aliases=aliases)

        model_id = service._resolve_model_alias("sonnet")
        assert model_id == "mistral-7b"

    def test_resolve_model_alias_case_insensitive(self):
        """Test alias resolution is case-insensitive."""
        aliases = {"opus": "neural-chat-7b"}
        service = InferenceService(model_aliases=aliases)

        assert service._resolve_model_alias("OPUS") == "neural-chat-7b"
        assert service._resolve_model_alias("OpUs") == "neural-chat-7b"

    def test_resolve_model_alias_unknown(self):
        """Test resolving unknown alias returns None."""
        aliases = {"haiku": "neural-chat-7b"}
        service = InferenceService(model_aliases=aliases)

        model_id = service._resolve_model_alias("unknown")
        assert model_id is None

    def test_resolve_model_alias_empty(self):
        """Test resolving empty string returns None."""
        aliases = {"haiku": "neural-chat-7b"}
        service = InferenceService(model_aliases=aliases)

        model_id = service._resolve_model_alias(None)
        assert model_id is None


@pytest.mark.asyncio
class TestRestrictedDataTier2Routing:
    """Test RESTRICTED data routing to Tier 2."""

    async def test_restricted_data_routes_to_tier2(self):
        """Test that RESTRICTED data is routed to Tier 2 only."""
        # Setup mocks
        external_llm = AsyncMock()
        external_llm.complete = AsyncMock(return_value=CompletionResponse(
            content="Processed with Tier 2",
            input_tokens=10,
            output_tokens=20,
            cache_hit=False,
            model_id="neural-chat-7b",
        ))

        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=external_llm,
            model_aliases={"opus": "neural-chat-7b"},
        )

        # Mock classifier to return RESTRICTED
        with patch.object(service._classifier, 'classify', return_value='RESTRICTED'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                # Submit inference
                request = InferenceRequest(
                    prompt="Sensitive data",
                    team_id="team1",
                    user_id="user1",
                    model="opus",
                )
                job_id = service.enqueue(request)

                # Wait for async task
                import asyncio
                await asyncio.sleep(0.1)

                # Verify Tier 2 was called
                assert external_llm.complete.called
                job_result = service.get_job(job_id)
                assert job_result.status == "completed"
                assert job_result.tier == 2
                assert job_result.provider == "external_llm"
                assert job_result.data_classification == "RESTRICTED"

    async def test_restricted_data_without_tier2_fails(self):
        """Test that RESTRICTED data fails without Tier 2 provider."""
        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=None,  # No Tier 2
        )

        # Mock classifier to return RESTRICTED
        with patch.object(service._classifier, 'classify', return_value='RESTRICTED'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                # Submit inference
                request = InferenceRequest(
                    prompt="Sensitive data",
                    team_id="team1",
                    user_id="user1",
                )
                job_id = service.enqueue(request)

                # Wait for async task
                import asyncio
                await asyncio.sleep(0.1)

                # Verify job failed
                job_result = service.get_job(job_id)
                assert job_result.status == "failed"
                assert "No Tier 2 model available" in job_result.error or "Tier 2" in job_result.error

    async def test_restricted_data_defaults_to_opus(self):
        """Test that RESTRICTED data defaults to opus model if not specified."""
        # Setup mocks
        external_llm = AsyncMock()
        external_llm.complete = AsyncMock(return_value=CompletionResponse(
            content="Default to opus",
            input_tokens=10,
            output_tokens=20,
            cache_hit=False,
            model_id="neural-chat-7b",
        ))

        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=external_llm,
            model_aliases={"opus": "neural-chat-7b"},
        )

        # Mock classifier to return RESTRICTED
        with patch.object(service._classifier, 'classify', return_value='RESTRICTED'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                # Submit inference without specifying model
                request = InferenceRequest(
                    prompt="Sensitive data",
                    team_id="team1",
                    user_id="user1",
                )
                job_id = service.enqueue(request)

                # Wait for async task
                import asyncio
                await asyncio.sleep(0.1)

                # Verify job succeeded with opus
                job_result = service.get_job(job_id)
                assert job_result.status == "completed"
                assert job_result.model_alias == "opus"


@pytest.mark.asyncio
class TestTier2Failover:
    """Test Tier 2 failover and error handling."""

    async def test_tier2_timeout_returns_error(self):
        """Test that Tier 2 timeout is properly handled."""
        # Setup mock that raises timeout
        external_llm = AsyncMock()
        external_llm.complete = AsyncMock(side_effect=Exception("Timeout"))

        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=external_llm,
            model_aliases={"opus": "neural-chat-7b"},
        )

        # Mock classifier to return RESTRICTED
        with patch.object(service._classifier, 'classify', return_value='RESTRICTED'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                # Submit inference
                request = InferenceRequest(
                    prompt="Sensitive data",
                    team_id="team1",
                    user_id="user1",
                )
                job_id = service.enqueue(request)

                # Wait for async task
                import asyncio
                await asyncio.sleep(0.1)

                # Verify job failed with error
                job_result = service.get_job(job_id)
                assert job_result.status == "failed"
                assert "Timeout" in job_result.error

    async def test_tier2_all_endpoints_down(self):
        """Test that all endpoints down error is properly handled."""
        # Setup mock that indicates no endpoints available
        external_llm = AsyncMock()
        external_llm.complete = AsyncMock(
            side_effect=Exception("Tier 2 service unavailable: all endpoints are down")
        )

        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=external_llm,
            model_aliases={"opus": "neural-chat-7b"},
        )

        # Mock classifier to return RESTRICTED
        with patch.object(service._classifier, 'classify', return_value='RESTRICTED'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                # Submit inference
                request = InferenceRequest(
                    prompt="Sensitive data",
                    team_id="team1",
                    user_id="user1",
                )
                job_id = service.enqueue(request)

                # Wait for async task
                import asyncio
                await asyncio.sleep(0.1)

                # Verify job failed with appropriate error
                job_result = service.get_job(job_id)
                assert job_result.status == "failed"
                assert "all endpoints are down" in job_result.error


@pytest.mark.asyncio
class TestNonRestrictedDataTier1Fallback:
    """Test non-RESTRICTED data uses Tier 1 with Tier 2 fallback."""

    async def test_non_restricted_uses_tier1(self):
        """Test that non-RESTRICTED data routes to Tier 1."""
        service = InferenceService(
            health=ProviderHealth(),
            budget=BudgetService(),
            audit=AuditLogger(),
            pii_masker=PIIMasker(),
            external_llm_provider=None,  # Tier 2 not needed
        )

        # Mock classifier to return PUBLIC
        with patch.object(service._classifier, 'classify', return_value='PUBLIC'):
            with patch.object(service._pii_masker, 'mask', return_value=('prompt', {})):
                with patch.object(service._router, 'route') as mock_route:
                    # Mock route to return Tier 1 config
                    from src.aegis.models import ModelConfig
                    mock_route.return_value = ModelConfig(
                        alias="haiku",
                        provider="anthropic",
                        tier=1,
                        model_id="claude-3-haiku",
                        cost_input_per_mtok=0.80,
                        cost_output_per_mtok=4.0,
                    )

                    with patch('src.aegis.services.inference.ProviderFactory') as mock_factory:
                        mock_provider = AsyncMock()
                        mock_provider.complete = AsyncMock(return_value=CompletionResponse(
                            content="Tier 1 response",
                            input_tokens=10,
                            output_tokens=20,
                            cache_hit=False,
                            model_id="claude-3-haiku",
                        ))
                        mock_provider.estimate_cost_usd = MagicMock(return_value=0.1)
                        mock_factory.get.return_value = mock_provider

                        # Submit inference
                        request = InferenceRequest(
                            prompt="Public data",
                            team_id="team1",
                            user_id="user1",
                        )
                        job_id = service.enqueue(request)

                        # Wait for async task
                        import asyncio
                        await asyncio.sleep(0.1)

                        # Verify Tier 1 was used
                        job_result = service.get_job(job_id)
                        assert job_result.tier == 1
                        assert job_result.provider == "anthropic"


@pytest.mark.asyncio
class TestModelAliasInInference:
    """Test that model alias parameter works in inference requests."""

    async def test_inference_request_with_model_alias(self):
        """Test that model parameter is accepted in inference request."""
        request = InferenceRequest(
            prompt="Test",
            team_id="team1",
            user_id="user1",
            model="haiku",
        )

        assert request.model == "haiku"

    async def test_inference_request_without_model_alias(self):
        """Test that model parameter is optional."""
        request = InferenceRequest(
            prompt="Test",
            team_id="team1",
            user_id="user1",
        )

        assert request.model is None
