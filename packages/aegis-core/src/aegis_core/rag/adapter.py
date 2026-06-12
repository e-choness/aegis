"""LangChainVectorStoreAdapter — wraps any LangChain VectorStore as a VectorStoreProvider."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aegis_core.rag.protocol import Doc


class LangChainVectorStoreAdapter:
    """Implements the :class:`~aegis_core.rag.protocol.VectorStoreProvider` protocol
    by wrapping per-namespace LangChain ``VectorStore`` instances.

    Each namespace gets its own ``VectorStore`` instance created lazily via
    *store_factory*.  This provides clean, store-agnostic namespace isolation:

    - For Chroma the factory creates a new ``Collection`` per namespace.
    - For pgvector the factory creates a new ``PGVector`` table per namespace.

    Args:
        store_factory: Callable ``(namespace: str) -> VectorStore`` that is
            called at most once per namespace and must return a fully
            initialised LangChain ``VectorStore`` with its embedding function
            already configured.
        embedder: Optional embedding provider; stored for introspection.
        name: Identifier for this adapter.
    """

    def __init__(
        self,
        store_factory: Callable[[str], Any],
        embedder: Any = None,
        name: str = "langchain",
    ) -> None:
        self.name = name
        self._factory = store_factory
        self._embedder = embedder
        self._stores: dict[str, Any] = {}

    def _get_store(self, namespace: str) -> Any:
        if namespace not in self._stores:
            self._stores[namespace] = self._factory(namespace)
        return self._stores[namespace]

    async def add(self, docs: list[Doc], namespace: str) -> None:
        """Embed and persist *docs* in *namespace* via the underlying store."""
        from langchain_core.documents import Document as LCDoc

        store = self._get_store(namespace)
        lc_docs = [
            LCDoc(page_content=d.text, id=d.id, metadata=d.metadata or {})
            for d in docs
        ]
        await store.aadd_documents(lc_docs)

    async def query(
        self, vector: list[float], namespace: str, k: int
    ) -> list[Doc]:
        """Return up to *k* docs from *namespace* nearest to *vector*."""
        store = self._get_store(namespace)
        results = await store.asimilarity_search_by_vector(vector, k=k)
        return [Doc(text=r.page_content, metadata=r.metadata) for r in results]
