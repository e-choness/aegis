"""Chroma dev vector store — per-namespace collections via the Chroma client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def make_chroma_store_factory(
    client: Any | None = None,
    embedding_function: Any | None = None,
) -> Callable[[str], Any]:
    """Return a store factory that creates a Chroma collection per namespace.

    Suitable for :class:`~aegis_core.rag.adapter.LangChainVectorStoreAdapter`.

    Args:
        client: An existing ``chromadb.Client``.  Defaults to
            ``chromadb.EphemeralClient()`` (in-memory, no persistence).
            Pass ``chromadb.PersistentClient(path=...)`` for durability.
        embedding_function: A LangChain ``Embeddings`` implementation used to
            embed texts at index time.  The same function (or one producing
            identical vectors) must be used when embedding queries.

    Returns:
        A callable ``(namespace: str) -> langchain_chroma.Chroma``.

    Raises:
        ImportError: If ``chromadb`` or ``langchain-chroma`` are not installed.
            Install the ``[rag]`` extra: ``pip install aegis-core[rag]``.
    """
    import chromadb
    from langchain_chroma import Chroma

    _client = client if client is not None else chromadb.EphemeralClient()

    def factory(namespace: str) -> Any:
        return Chroma(
            collection_name=namespace,
            embedding_function=embedding_function,
            client=_client,
        )

    return factory
