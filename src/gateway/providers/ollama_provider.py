from __future__ import annotations
import logging
import httpx
from .base import LLMProvider, CompletionRequest, CompletionResponse

logger = logging.getLogger("aegis.provider.ollama")

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    """
    Tier 2/3 (local/offline) provider. No network dependency beyond localhost.
    Primary provider for RESTRICTED data (never touches cloud).
    Also serves as final fallback when all cloud providers are down.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        logger.info("OllamaProvider using base_url=%s", self._base_url)
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        logger.info("Ollama complete: model=%s, url=%s/api/generate", request.model_id, self._base_url)
        payload: dict = {
            "model": request.model_id,
            "prompt": request.prompt,
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()

        content = data.get("response", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)

        return CompletionResponse(
            content=content,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            cache_hit=False,
            model_id=request.model_id,
        )

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int, alias: str) -> float:
        return 0.0

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False
