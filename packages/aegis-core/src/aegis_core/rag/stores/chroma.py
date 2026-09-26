"""ChromaVectorStore — in-process Chroma backed VectorStoreProvider.

Uses the chromadb Python client directly (no LangChain dependency here).
Lazy-imports chromadb so that the module can be imported even when the
``[rag]`` extra is not installed — the ``ImportError`` surfaces only when
an instance is constructed.

Namespaces map 1-to-1 to Chroma collection names.
"""

from __future__ import annotations

from typing import Any

from aegis_core.rag.protocol import Doc, EmbeddingProvider


class ChromaVectorStore:
    """Chromadb-backed :class:`~aegis_core.rag.protocol.VectorStoreProvider`.

    Args:
        embedder: Used to embed documents at index time and externally to
            embed queries before calling :meth:`query`.
        path: If *None* (default), an in-memory ``EphemeralClient`` is used.
            Pass a directory path for a persistent ``PersistentClient``.
        name: Identifier shown in events.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        path: str | None = None,
        name: str = "chroma",
    ) -> None:
        import chromadb  # lazy import — requires [rag] extra

        self.name = name
        self._embedder = embedder
        self._client: Any = (
            chromadb.EphemeralClient()
            if path is None
            else chromadb.PersistentClient(path=path)
        )
        self._collections: dict[str, Any] = {}

    def _get_collection(self, namespace: str) -> Any:
        # Chroma requires 3-512 chars from [a-zA-Z0-9._-]; the prefix makes short
        # namespaces ("hr") valid and keeps Aegis collections apart from others
        # in a shared Chroma instance.
        if namespace not in self._collections:
            self._collections[namespace] = self._client.get_or_create_collection(
                f"aegis-{namespace}"
            )
        return self._collections[namespace]

    async def add(self, docs: list[Doc], namespace: str) -> None:
        """Embed and index *docs* into *namespace*."""
        if not docs:
            return
        col = self._get_collection(namespace)
        embeddings = await self._embedder.embed([d.text for d in docs])
        col.add(
            ids=[d.id for d in docs],
            embeddings=embeddings,
            documents=[d.text for d in docs],
            metadatas=[d.metadata if d.metadata else None for d in docs],
        )

    async def query(
        self, vector: list[float], namespace: str, k: int
    ) -> list[Doc]:
        """Return the *k* most similar docs from *namespace*."""
        col = self._get_collection(namespace)
        count = col.count()
        if count == 0:
            return []
        found = col.query(
            query_embeddings=[vector],
            n_results=min(k, count),
            include=["documents", "metadatas"],
        )
        ids = found["ids"][0]
        texts = (found["documents"] or [[]])[0]
        metas = (found["metadatas"] or [[]])[0]
        return [
            Doc(id=doc_id, text=texts[i], metadata=dict(metas[i] or {}))
            for i, doc_id in enumerate(ids)
        ]
