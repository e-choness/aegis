from __future__ import annotations
import logging
import os
from typing import Optional
import httpx
from .base import LLMProvider, CompletionRequest, CompletionResponse

logger = logging.getLogger("aegis.provider.vllm")

# Amortized GPU cost: 2× A100 80GB ÷ expected utilization
_AMORTIZED_COST_PER_MTOK = 0.10


class VLLMProvider(LLMProvider):
    """
    Tier 2 self-hosted provider. Handles ALL data classifications including RESTRICTED.
    Uses vLLM's OpenAI-compatible /v1/chat/completions API.
    Hardware: minimum 2× NVIDIA A100 80GB (43GB VRAM for 70B at Q4_K_M).
    Long timeout (300s) for 70B inference at load.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        url = base_url or os.environ.get("VLLM_BASE_URL", "http://vllm:8001")
        self._base_url = url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=300.0)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        response = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json={
                "model": request.model_id,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        )
        response.raise_for_status()
        data = response.json()

        usage = data.get("usage", {})
        return CompletionResponse(
            content=data["choices"][0]["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=False,
            model_id=request.model_id,
        )

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        return (input_tokens + output_tokens) * _AMORTIZED_COST_PER_MTOK / 1_000_000

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("vLLM health check failed: %s", exc)
            return False
