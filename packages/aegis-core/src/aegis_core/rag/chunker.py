"""TextChunker — splits documents into indexable Doc fragments.

Wraps langchain-text-splitters (part of the ``[rag]`` extra) so the rest of
the codebase does not import LangChain text-splitting directly.
"""

from __future__ import annotations

import uuid
from typing import Any

from aegis_core.rag.protocol import Doc


class TextChunker:
    """Split text into fixed-size overlapping chunks for indexing.

    Args:
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap in characters between adjacent chunks.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Doc]:
        """Split *text* into :class:`~aegis_core.rag.protocol.Doc` fragments.

        Args:
            text: Source text to split.
            metadata: Base metadata attached to every produced chunk.

        Returns:
            List of :class:`Doc` instances with unique IDs and chunk text.
        """
        chunks = self._splitter.split_text(text)
        base = metadata or {}
        return [Doc(id=str(uuid.uuid4()), text=chunk, metadata=dict(base)) for chunk in chunks]

    def split_many(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> list[Doc]:
        """Split multiple texts, each with optional per-text metadata.

        Args:
            texts: Source texts to split.
            metadatas: Per-text metadata dicts (must match *texts* length if
                provided, otherwise empty dicts are used).

        Returns:
            Flat list of :class:`Doc` instances across all input texts.
        """
        metas: list[dict[str, Any]] = metadatas if metadatas is not None else [{} for _ in texts]
        docs: list[Doc] = []
        for text, meta in zip(texts, metas, strict=False):
            docs.extend(self.split(text, meta))
        return docs
