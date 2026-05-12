"""Tests for ExternalLLMProvider (Tier 2)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from aegis.providers.external_llm_provider import ExternalLLMProvider
from aegis.providers.base import CompletionRequest, CompletionResponse
from aegis.services.model_cache import ModelCache, ModelInfo
from aegis.services.tier2_failover import Tier2Failover, EndpointConfig
from aegis.services.auth_manager import AuthManager, AuthConfig


@pytest.fixture
def setup_provider():
    """Setup a test ExternalLLMProvider."""
    endpoints = [
        EndpointConfig(url="http://localhost:8000", weight=1),
        EndpointConfig(url="http://localhost:8001", weight=1),
    ]
    cache = ModelCache(ttl_seconds=300)
    failover = Tier2Failover(endpoints=endpoints)
    auth_config = AuthConfig(auth_type="api_key")
    auth_config.token = "test-token"
    auth_manager = AuthManager(auth_config)

    provider = ExternalLLMProvider(
        endpoints=endpoints,
        auth_manager=auth_manager,
        cache=cache,
        failover=failover,
        timeout_seconds=5.0,
    )

    return provider, failover, cache


@pytest.mark.asyncio
class TestExternalLLMProviderCompletion:
    """Test ExternalLLMProvider completion requests."""

    async def test_complete_request(self, setup_provider):
        """Test sending a completion request to Tier 2."""
        provider, failover, cache = setup_provider

        # Mock the endpoint selection
        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            # Mock the HTTP request
            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value={
                    "choices": [{"text": "This is the response"}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                    }
                })

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                # Send completion request
                request = CompletionRequest(
                    model_id="neural-chat-7b",
                    prompt="Test prompt",
                    max_tokens=100,
                    temperature=0.7,
                )

                response = await provider.complete(request)

                assert response.content == "This is the response"
                assert response.input_tokens == 10
                assert response.output_tokens == 20
                mock_select.assert_called_once()

    async def test_complete_request_with_system_prompt(self, setup_provider):
        """Test completion request includes system prompt."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value={
                    "choices": [{"text": "Response"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20}
                })

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                request = CompletionRequest(
                    model_id="neural-chat-7b",
                    prompt="Test prompt",
                    system_prompt="You are helpful",
                    max_tokens=100,
                    temperature=0.7,
                )

                response = await provider.complete(request)

                # Verify system prompt was included in payload
                call_args = mock_client.post.call_args
                assert "json" in call_args.kwargs
                payload = call_args.kwargs["json"]
                assert payload.get("system") == "You are helpful"

    async def test_complete_request_no_healthy_endpoints(self, setup_provider):
        """Test completion fails when no healthy endpoints available."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = None  # No healthy endpoints

            request = CompletionRequest(
                model_id="neural-chat-7b",
                prompt="Test prompt",
            )

            with pytest.raises(Exception) as exc_info:
                await provider.complete(request)

            assert "unavailable" in str(exc_info.value).lower()

    async def test_complete_request_timeout(self, setup_provider):
        """Test completion request timeout handling."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
                mock_client_class.return_value = mock_client

                with patch.object(failover, 'mark_endpoint_failed'):
                    request = CompletionRequest(
                        model_id="neural-chat-7b",
                        prompt="Test prompt",
                    )

                    with pytest.raises(Exception) as exc_info:
                        await provider.complete(request)

                    assert "unavailable" in str(exc_info.value).lower()

    async def test_complete_request_server_error(self, setup_provider):
        """Test completion request handles server errors."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            # First call fails, second succeeds
            mock_select.side_effect = ["http://localhost:8000", "http://localhost:8001"]

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                # First response is 500, second is 200
                mock_response_500 = MagicMock()
                mock_response_500.status_code = 500
                mock_response_500.text = "Internal Server Error"

                mock_response_200 = MagicMock()
                mock_response_200.status_code = 200
                mock_response_200.json = MagicMock(return_value={
                    "choices": [{"text": "Response"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20}
                })

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.post = AsyncMock(side_effect=[mock_response_500, mock_response_200])
                mock_client_class.return_value = mock_client

                with patch.object(failover, 'mark_endpoint_failed'):
                    with patch.object(failover, 'mark_endpoint_healthy'):
                        with patch.object(failover, 'increment_failover_count'):
                            request = CompletionRequest(
                                model_id="neural-chat-7b",
                                prompt="Test prompt",
                            )

                            response = await provider.complete(request)

                            assert response.content == "Response"


@pytest.mark.asyncio
class TestExternalLLMProviderDiscovery:
    """Test ExternalLLMProvider model discovery."""

    async def test_discover_models(self, setup_provider):
        """Test discovering models from Tier 2."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value={
                    "data": [
                        {"id": "neural-chat-7b", "context_length": 4096},
                        {"id": "mistral-7b", "context_length": 8192},
                    ]
                })

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                with patch.object(failover, 'mark_endpoint_healthy'):
                    models = await provider.discover_models()

                    assert len(models) == 2
                    assert models[0].id == "neural-chat-7b"
                    assert models[1].id == "mistral-7b"

                    # Verify cache was updated
                    cached = cache.get("tier_2")
                    assert len(cached.models) == 2


@pytest.mark.asyncio
class TestExternalLLMProviderHealth:
    """Test ExternalLLMProvider health checks."""

    async def test_health_check_success(self, setup_provider):
        """Test successful health check."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                with patch.object(failover, 'mark_endpoint_healthy'):
                    is_healthy = await provider.health_check()

                    assert is_healthy is True

    async def test_health_check_failure(self, setup_provider):
        """Test failed health check."""
        provider, failover, cache = setup_provider

        with patch.object(failover, 'select_endpoint', new_callable=AsyncMock) as mock_select:
            mock_select.return_value = "http://localhost:8000"

            with patch('aegis.providers.external_llm_provider.httpx.AsyncClient') as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 500

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                with patch.object(failover, 'mark_endpoint_failed'):
                    is_healthy = await provider.health_check()

                    assert is_healthy is False


class TestExternalLLMProviderCost:
    """Test ExternalLLMProvider cost calculation."""

    def test_estimate_cost_is_zero(self, setup_provider):
        """Test that Tier 2 cost estimation returns 0."""
        provider, _, _ = setup_provider

        cost = provider.estimate_cost_usd(100, 200, "neural-chat-7b")

        assert cost == 0.0
