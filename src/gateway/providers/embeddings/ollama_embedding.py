from __future__ import annotations
import logging
import os
from typing import Optional
import httpx
from .base import EmbeddingProvider

logger = logging.getLogger("aegis.embedding.ollama")

_DEFAULT_MODEL = "nomic-embed-text"


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Tier 3 offline embedding — nomic-embed-text (768-dim, 274MB, all classifications).
    Outperforms ada-002 on retrieval benchmarks. No network required.
    Pre-pull: ollama pull nomic-embed-text

    Always available as final fallback (no cloud dependency).
    """

    dimensions = 768

    def __init__(self, base_url: Optional[str] = None, model: str = _DEFAULT_MODEL) -> None:
        url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self._base_url = url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Ollama /api/embed accepts batch input
        response = await self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama embedding health check failed: %s", exc)
            return False
