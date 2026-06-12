"""Text chunking helpers — thin wrapper around langchain-text-splitters."""

from __future__ import annotations


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split *text* into overlapping chunks suitable for embedding.

    Uses :class:`langchain_text_splitters.RecursiveCharacterTextSplitter`
    which tries to split at paragraph, sentence, and word boundaries before
    resorting to character splits.

    Args:
        text: Full document text to split.
        chunk_size: Target character length per chunk.
        chunk_overlap: Number of characters to repeat between adjacent chunks
            to preserve cross-boundary context.

    Returns:
        A list of non-empty string chunks.

    Raises:
        ImportError: If ``langchain-text-splitters`` is not installed.
            Install the ``[rag]`` extra: ``pip install aegis-core[rag]``.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_text(text)
