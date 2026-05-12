from __future__ import annotations
import os
import logging
from typing import Optional
import anthropic
from .base import LLMProvider, CompletionRequest, CompletionResponse

logger = logging.getLogger("aegis.provider.anthropic")

# Opus 4.7 tokenizer generates up to 35% more tokens vs 4.6 — apply safety margin
OPUS_TOKENIZER_MARGIN = 1.35

PRICING: dict[str, tuple[float, float]] = {
    "haiku":  (1.00, 5.00),
    "sonnet": (3.00, 15.00),
    "opus":   (5.00, 25.00),
}


class AnthropicProvider(LLMProvider):
    """
    Tier 1 primary. Uses Anthropic Python SDK with prompt caching on system prompts.
    API key fetched from environment (Vault injection in production).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.AsyncAnthropic(api_key=key)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = [{"role": "user", "content": request.prompt}]

        kwargs: dict = {
            "model": request.model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }

        if request.system_prompt:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": request.system_prompt,
                    "cache_control": {"type": "ephemeral"} if request.use_cache else None,
                }
            ]
            if not request.use_cache:
                kwargs["system"] = [{"type": "text", "text": request.system_prompt}]

        response = await self._client.messages.create(**kwargs)

        cache_hit = (
            hasattr(response.usage, "cache_read_input_tokens")
            and (response.usage.cache_read_input_tokens or 0) > 0
        )

        return CompletionResponse(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_hit=cache_hit,
            model_id=request.model_id,
        )

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        input_rate, output_rate = PRICING.get(alias, PRICING["sonnet"])
        base = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        margin = OPUS_TOKENIZER_MARGIN if alias == "opus" else 1.0
        return base * margin

    async def health_check(self) -> bool:
        try:
            # Minimal call to haiku to verify connectivity
            await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as exc:
            logger.warning("Anthropic health check failed: %s", exc)
            return False
