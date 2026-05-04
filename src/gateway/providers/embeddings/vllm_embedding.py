from __future__ import annotations
import logging
import os
from typing import Optional
import httpx
from .base import EmbeddingProvider

logger = logging.getLogger("aegis.embedding.vllm")

_DEFAULT_MODEL = "bge-m3"


class VLLMEmbeddingProvider(EmbeddingProvider):
    """
    Tier 2 embedding — BGE-M3 via vLLM (768-dim, multilingual, all classifications).
    Supports French (required for Canadian bilingual content under PIPEDA).
    Uses vLLM's OpenAI-compatible /v1/embeddings endpoint.
    """

    dimensions = 768

    def __init__(self, base_url: Optional[str] = None, model: str = _DEFAULT_MODEL) -> None:
        url = base_url or os.environ.get("VLLM_BASE_URL", "http://vllm:8001")
        self._base_url = url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self._base_url}/v1/embeddings",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("vLLM embedding health check failed: %s", exc)
            return False
