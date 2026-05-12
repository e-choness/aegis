from __future__ import annotations
import json
import logging
import httpx
from typing import List, Optional

from .base import LLMProvider, CompletionRequest, CompletionResponse, ModelStatus
from ..services.model_cache import ModelCache, ModelInfo
from ..services.tier2_failover import Tier2Failover, EndpointConfig
from ..services.auth_manager import AuthManager

logger = logging.getLogger("aegis.external_llm_provider")


class ExternalLLMProvider(LLMProvider):
    """
    OpenAI-compatible Tier 2 provider (LM Studio, vLLM, external Ollama).
    - Forwards requests to /v1/completions endpoint
    - Discovers models via /v1/models
    - Implements failover and circuit breaker logic
    - Supports Bearer token and mTLS authentication
    """

    def __init__(
        self,
        endpoints: List[EndpointConfig],
        auth_manager: AuthManager,
        cache: ModelCache,
        failover: Tier2Failover,
        timeout_seconds: float = 5.0,
    ):
        self._endpoints = endpoints
        self._auth_manager = auth_manager
        self._cache = cache
        self._failover = failover
        self._timeout_seconds = timeout_seconds

        logger.info(
            "ExternalLLMProvider initialized with %d endpoints, timeout=%fs",
            len(endpoints),
            timeout_seconds,
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Forward completion request to Tier 2 /v1/completions endpoint.
        Implements failover: try endpoint 1 → endpoint 2 → fail if all exhausted.
        """
        max_retries = len(self._endpoints)
        last_error = None

        for attempt in range(max_retries):
            endpoint_url = await self._failover.select_endpoint()
            if not endpoint_url:
                logger.error("No healthy endpoints available for completion")
                raise Exception("Tier 2 service unavailable: all endpoints are down")

            try:
                logger.info(
                    "Attempt %d: forwarding completion to %s (model=%s)",
                    attempt + 1,
                    endpoint_url,
                    request.model_id,
                )

                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    # Prepare headers with auth injection
                    headers = {}
                    headers = self._auth_manager.inject_headers(headers)

                    # Build OpenAI-compatible payload
                    payload = {
                        "model": request.model_id,
                        "prompt": request.prompt,
                        "max_tokens": request.max_tokens,
                        "temperature": request.temperature,
                    }
                    if request.system_prompt:
                        payload["system"] = request.system_prompt

                    # POST to /v1/completions
                    full_url = f"{endpoint_url}/v1/completions"
                    response = await client.post(full_url, json=payload, headers=headers)

                    if response.status_code >= 500:
                        logger.warning(
                            "Tier 2 returned %d: %s", response.status_code, response.text
                        )
                        self._failover.mark_endpoint_failed(endpoint_url)
                        self._failover.increment_failover_count()
                        continue

                    response.raise_for_status()

                    # Parse response
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("text", "")
                    usage = data.get("usage", {})
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)

                    # Mark endpoint as healthy
                    self._failover.mark_endpoint_healthy(endpoint_url)

                    logger.info(
                        "Completion successful from %s (tokens: %d+%d)",
                        endpoint_url,
                        input_tokens,
                        output_tokens,
                    )

                    return CompletionResponse(
                        content=content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_hit=False,
                        model_id=request.model_id,
                    )

            except httpx.TimeoutException as e:
                logger.warning("Timeout on %s: %s", endpoint_url, e)
                self._failover.mark_endpoint_failed(endpoint_url)
                self._failover.increment_failover_count()
                last_error = e

            except httpx.ConnectError as e:
                logger.warning("Connection error on %s: %s", endpoint_url, e)
                self._failover.mark_endpoint_failed(endpoint_url)
                self._failover.increment_failover_count()
                last_error = e

            except Exception as e:
                logger.error("Error on %s: %s", endpoint_url, e)
                self._failover.mark_endpoint_failed(endpoint_url)
                self._failover.increment_failover_count()
                last_error = e

        # All endpoints exhausted
        logger.error("All Tier 2 endpoints exhausted for completion")
        raise Exception(
            f"Tier 2 service unavailable after {max_retries} attempts: {last_error}"
        )

    async def discover_models(self) -> List[ModelInfo]:
        """
        Query Tier 2 /v1/models endpoint and populate cache.
        Returns list of available models.
        """
        endpoint_url = await self._failover.select_endpoint()
        if not endpoint_url:
            logger.error("No healthy endpoints for model discovery")
            return []

        try:
            logger.info("Discovering models from %s/v1/models", endpoint_url)

            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                headers = self._auth_manager.inject_headers({})
                full_url = f"{endpoint_url}/v1/models"

                response = await client.get(full_url, headers=headers)
                response.raise_for_status()

                data = response.json()
                models = []

                for model_data in data.get("data", []):
                    model_info = ModelInfo(
                        id=model_data.get("id"),
                        context_length=model_data.get("context_length", 4096),
                        supports_function_calling=model_data.get(
                            "supports_function_calling", False
                        ),
                        estimated_cost_per_mtok=0.0,  # Tier 2 = zero cost
                    )
                    models.append(model_info)

                # Update cache
                self._cache.set("tier_2", models)
                logger.info("Model discovery complete: %d models cached", len(models))

                self._failover.mark_endpoint_healthy(endpoint_url)
                return models

        except Exception as e:
            logger.error("Model discovery failed on %s: %s", endpoint_url, e)
            self._failover.mark_endpoint_failed(endpoint_url)
            return []

    async def health_check(self) -> bool:
        """Query /v1/models for health status."""
        try:
            endpoint_url = await self._failover.select_endpoint()
            if not endpoint_url:
                return False

            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                headers = self._auth_manager.inject_headers({})
                response = await client.get(f"{endpoint_url}/v1/models", headers=headers)

                if response.status_code == 200:
                    self._failover.mark_endpoint_healthy(endpoint_url)
                    logger.debug("Health check OK for %s", endpoint_url)
                    return True
                else:
                    self._failover.mark_endpoint_failed(endpoint_url)
                    return False

        except Exception as e:
            logger.warning("Health check failed: %s", e)
            return False

    async def get_model_status(self, model_id: str) -> ModelStatus:
        """Check if model exists in cached list."""
        cached = self._cache.get("tier_2")
        if not cached:
            return ModelStatus.UNKNOWN

        for model in cached.models:
            if model.id == model_id:
                return ModelStatus.READY

        return ModelStatus.UNKNOWN

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        """Tier 2 is self-hosted, so no cost."""
        return 0.0
