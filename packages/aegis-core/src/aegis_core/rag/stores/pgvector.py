"""PgVectorStore — PostgreSQL/pgvector backed VectorStoreProvider.

Uses ``langchain-postgres`` (part of the ``[rag]`` extra) via the
:class:`~aegis_core.rag.adapter.LangChainVectorStoreAdapter`.

Connection string format: ``postgresql+psycopg://user:pass@host:port/dbname``
(psycopg 3 driver, already a transitive dependency of
``langgraph-checkpoint-postgres``).
"""

from __future__ import annotations

import asyncio

from aegis_core.rag.adapter import LangChainVectorStoreAdapter
from aegis_core.rag.protocol import Doc, EmbeddingProvider


class _EmbeddingBridge:
    """Sync LangChain ``Embeddings`` adapter for an async :class:`EmbeddingProvider`."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.run(self._provider.embed(texts))

    def embed_query(self, text: str) -> list[float]:
        return asyncio.run(self._provider.embed([text]))[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._provider.embed(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return (await self._provider.embed([text]))[0]


class PgVectorStore:
    """pgvector-backed :class:`~aegis_core.rag.protocol.VectorStoreProvider`.

    Args:
        embedder: Aegis :class:`~aegis_core.rag.protocol.EmbeddingProvider`.
        conn_str: psycopg 3 connection string, e.g.
            ``postgresql+psycopg://aegis:aegis@postgres:5432/aegis``.
        name: Identifier shown in events.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        conn_str: str,
        name: str = "pgvector",
    ) -> None:
        self.name = name
        self._embedder = embedder
        bridge = _EmbeddingBridge(embedder)

        def _factory(namespace: str) -> object:
            from langchain_postgres.vectorstores import PGVector  # lazy import

            return PGVector(
                embeddings=bridge,  # type: ignore[arg-type]
                collection_name=namespace,
                connection=conn_str,
                use_jsonb=True,
            )

        self._adapter = LangChainVectorStoreAdapter(
            store_factory=_factory,
            embedder=embedder,
            name=name,
        )
        # Expose the bridge so callers can pass it as a LangChain embeddings object.
        self.bridge = bridge

    async def add(self, docs: list[Doc], namespace: str) -> None:
        """Embed and index *docs* into *namespace*."""
        await self._adapter.add(docs, namespace)

    async def query(
        self, vector: list[float], namespace: str, k: int
    ) -> list[Doc]:
        """Return the *k* most similar docs from *namespace*."""
        return await self._adapter.query(vector, namespace, k)
