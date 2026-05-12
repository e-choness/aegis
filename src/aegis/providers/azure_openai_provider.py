from __future__ import annotations
import logging
import os
from typing import Optional
import httpx
from .base import LLMProvider, CompletionRequest, CompletionResponse

logger = logging.getLogger("aegis.provider.azure")

# Same pricing as Anthropic tier 1 — Azure AI Foundry passes through Anthropic billing
PRICING: dict[str, tuple[float, float]] = {
    "haiku":  (1.00, 5.00),
    "sonnet": (3.00, 15.00),
    "opus":   (5.00, 25.00),
}

OPUS_TOKENIZER_MARGIN = 1.35
_API_VERSION = "2024-05-01-preview"


class AzureOpenAIProvider(LLMProvider):
    """
    Tier 1 secondary — Azure AI Foundry, Canada East region.
    PIPEDA-compliant: data stays within Canada.
    Uses Azure AI Inference API (OpenAI chat completions format).

    Requires env vars:
      AZURE_OPENAI_ENDPOINT  e.g. https://myresource.services.ai.azure.com
      AZURE_OPENAI_KEY       Azure API key
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        ep = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        key = api_key or os.environ.get("AZURE_OPENAI_KEY")
        if not ep or not key:
            raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set")
        self._endpoint = ep.rstrip("/")
        self._api_key = key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        response = await self._client.post(
            f"{self._endpoint}/models/chat/completions",
            params={"api-version": _API_VERSION},
            headers={
                "api-key": self._api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": request.model_id,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return CompletionResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=False,
            model_id=request.model_id,
        )

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        input_rate, output_rate = PRICING.get(alias, PRICING["sonnet"])
        base = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        margin = OPUS_TOKENIZER_MARGIN if alias == "opus" else 1.0
        return base * margin

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(
                f"{self._endpoint}/models",
                params={"api-version": _API_VERSION},
                headers={"api-key": self._api_key},
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Azure health check failed: %s", exc)
            return False
