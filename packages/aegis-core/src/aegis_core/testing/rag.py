"""RAG testing utilities: FakeEmbeddingProvider and FakeVectorStore."""

from __future__ import annotations

import hashlib
from typing import Any

from aegis_core.rag.protocol import Doc


class FakeEmbeddingProvider:
    """Deterministic fake embedding provider for unit tests.

    Each text is hashed at *dimensions* offsets to produce a reproducible
    fixed-length float vector, unless *embed_response* is given (fixed vector).

    Args:
        dimensions: Length of the embedding vector (default 16).
        embed_response: If set, every embed call returns this fixed vector.
        name: Provider name attribute.
    """

    name = "fake_embeddings"

    def __init__(
        self,
        dimensions: int = 16,
        embed_response: list[float] | None = None,
        name: str = "fake_embeddings",
    ) -> None:
        self._dimensions = dimensions
        self._embed_response = embed_response
        self.name = name
        self.embed_calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one deterministic embedding per text."""
        self.embed_calls.append(list(texts))
        if self._embed_response is not None:
            return [list(self._embed_response) for _ in texts]
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector: list[float] = []
        for i in range(self._dimensions):
            digest = hashlib.md5(f"{i}:{text}".encode()).digest()
            val = int.from_bytes(digest[:4], "big") / (2**32)
            vector.append(val)
        return vector

    def as_langchain_embeddings(self) -> Any:
        """Return a sync LangChain ``Embeddings``-compatible wrapper."""
        return _FakeLangChainEmbeddings(self)


class _FakeLangChainEmbeddings:
    """Synchronous LangChain ``Embeddings`` adapter wrapping :class:`FakeEmbeddingProvider`."""

    def __init__(self, provider: FakeEmbeddingProvider) -> None:
        self._provider = provider

    # Sync interface (required by most LangChain VectorStore constructors)
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._provider._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._provider._embed_one(text)

    # Async interface (used by aadd_texts / asimilarity_search_by_vector)
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


class FakeVectorStore:
    """In-memory vector store for unit tests.

    Stores :class:`Doc` objects by namespace.  ``query`` returns all docs in
    the namespace (up to *k*) without any actual similarity computation —
    suitable for tests that only care about round-trip correctness.

    Args:
        name: Store name attribute.
    """

    name = "fake_vector_store"

    def __init__(self, name: str = "fake_vector_store") -> None:
        self.name = name
        self._store: dict[str, list[Doc]] = {}
        self.add_calls: list[tuple[list[Doc], str]] = []
        self.query_calls: list[tuple[list[float], str, int]] = []

    async def add(self, docs: list[Doc], namespace: str) -> None:
        """Store docs in namespace."""
        self.add_calls.append((list(docs), namespace))
        ns = self._store.setdefault(namespace, [])
        ns.extend(docs)

    async def query(
        self, vector: list[float], namespace: str, k: int = 4
    ) -> list[Doc]:
        """Return up to *k* docs from *namespace* (insertion order)."""
        self.query_calls.append((list(vector), namespace, k))
        return list(self._store.get(namespace, []))[:k]
