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
        if response.status_code == 404:
            body = response.json()
            err = body.get("error", "")
            if "not found" in err:
                logger.info("Model %s not found locally — pulling now (this may take a minute)", self._model)
                await self._pull_model()
                response = await self._client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": texts},
                )
            response.raise_for_status()
        else:
            response.raise_for_status()
        data = response.json()
        return data["embeddings"]

    async def _pull_model(self) -> None:
        """Pulls the model from the Ollama registry, blocking until complete."""
        pull_resp = await self._client.post(
            f"{self._base_url}/api/pull",
            json={"model": self._model, "stream": False},
            timeout=600.0,  # large models can take several minutes
        )
        pull_resp.raise_for_status()
        logger.info("Model %s pulled successfully", self._model)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama embedding health check failed: %s", exc)
            return False
