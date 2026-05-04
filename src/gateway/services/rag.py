from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING
from ..providers.embeddings.factory import EmbeddingProviderFactory

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger("aegis.rag")

_CHUNK_SIZE_WORDS = 400
_CHUNK_OVERLAP_WORDS = 50


class TextChunker:
    """Splits text into overlapping word-boundary chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = _CHUNK_SIZE_WORDS,
        overlap: int = _CHUNK_OVERLAP_WORDS,
    ) -> None:
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        chunks: list[str] = []
        step = max(1, self._chunk_size - self._overlap)
        i = 0
        while i < len(words):
            chunk_words = words[i : i + self._chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + self._chunk_size >= len(words):
                break
            i += step
        return chunks


class RAGService:
    """
    Retrieval-Augmented Generation pipeline backed by pgvector.
    All embedding access goes through EmbeddingProviderFactory — never hardcoded to a provider.
    ADR-003: RESTRICTED documents use 768-dim on-prem embeddings only.

    Requires a running vectordb (pgvector) instance.
    Initialize with an asyncpg connection pool from the app lifespan.
    """

    _TABLE = "document_chunks_768"

    def __init__(
        self,
        db_pool: "asyncpg.Pool",
        health_checker=None,
    ) -> None:
        self._pool = db_pool
        self._health_checker = health_checker
        self._chunker = TextChunker()

    async def index_document(
        self,
        document_id: str,
        content: str,
        data_classification: str = "INTERNAL",
        namespace: str = "default",
    ) -> int:
        chunks = self._chunker.chunk(content)
        if not chunks:
            return 0

        provider = EmbeddingProviderFactory.get(data_classification, self._health_checker)
        embeddings = await provider.embed(chunks)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    emb_str = "[" + ",".join(f"{v:.8f}" for v in emb) + "]"
                    await conn.execute(
                        f"""
                        INSERT INTO {self._TABLE}
                            (document_id, chunk_index, content, embedding, data_class, namespace)
                        VALUES ($1, $2, $3, $4::vector, $5, $6)
                        ON CONFLICT DO NOTHING
                        """,
                        document_id, i, chunk, emb_str, data_classification, namespace,
                    )

        logger.info("Indexed document=%s chunks=%d classification=%s", document_id, len(chunks), data_classification)
        return len(chunks)

    async def retrieve(
        self,
        query: str,
        namespace: str,
        data_classification: str = "INTERNAL",
        top_k: int = 5,
    ) -> list[dict]:
        provider = EmbeddingProviderFactory.get(data_classification, self._health_checker)
        query_emb = (await provider.embed([query]))[0]
        emb_str = "[" + ",".join(f"{v:.8f}" for v in query_emb) + "]"

        # Only return chunks whose classification matches or is less sensitive
        allowed = _allowed_classifications(data_classification)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT chunk_index, content, data_class,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM {self._TABLE}
                WHERE namespace = $2
                  AND data_class = ANY($3::text[])
                ORDER BY embedding <=> $1::vector
                LIMIT $4
                """,
                emb_str, namespace, list(allowed), top_k,
            )
        return [dict(r) for r in rows]

    @staticmethod
    def build_context(chunks: list[dict]) -> str:
        """Formats retrieved chunks as numbered context for the LLM prompt."""
        parts = [
            f"[Source {i + 1}] (similarity={c['similarity']:.2f})\n{c['content']}"
            for i, c in enumerate(chunks)
        ]
        return "\n\n---\n\n".join(parts)


def _allowed_classifications(request_classification: str) -> set[str]:
    """
    Returns classifications that can be shown in a response to a request
    of the given classification. A PUBLIC request cannot see INTERNAL chunks.
    """
    order = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    idx = order.index(request_classification) if request_classification in order else 1
    return set(order[: idx + 1])
