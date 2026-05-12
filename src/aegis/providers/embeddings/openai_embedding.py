from __future__ import annotations
import logging
import os
from typing import Optional
import httpx
from .base import EmbeddingProvider

logger = logging.getLogger("aegis.embedding.openai")

_API_URL = "https://api.openai.com/v1/embeddings"
_MODEL = "text-embedding-3-small"


class OpenAIEmbeddingProvider(EmbeddingProvider):


    dimensions = 1536

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"},
            timeout=60.0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            _API_URL,
            json={"model": _MODEL, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("https://api.openai.com/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("OpenAI embedding health check failed: %s", exc)
            return False
