"""pgvector production store — per-namespace collections via langchain-postgres."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def make_pgvector_store_factory(
    connection_string: str,
    embedding_function: Any,
) -> Callable[[str], Any]:
    """Return a store factory that creates a pgvector collection per namespace.

    Suitable for :class:`~aegis_core.rag.adapter.LangChainVectorStoreAdapter`.

    Each namespace maps to a separate ``langchain_postgres.PGVector`` collection
    (``langchain_pg_collection`` row + associated ``langchain_pg_embedding`` rows).

    Args:
        connection_string: PostgreSQL DSN in the form expected by ``psycopg``,
            e.g. ``postgresql+psycopg://aegis:aegis@localhost:5432/aegis``.
        embedding_function: A LangChain ``Embeddings`` implementation.

    Returns:
        A callable ``(namespace: str) -> PGVector``.

    Raises:
        ImportError: If ``langchain-postgres`` is not installed.
            Install the ``[rag]`` extra: ``pip install aegis-core[rag]``.
    """
    from langchain_postgres import PGVector

    def factory(namespace: str) -> Any:
        return PGVector(
            collection_name=namespace,
            connection=connection_string,
            embeddings=embedding_function,
        )

    return factory
