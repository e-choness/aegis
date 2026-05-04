"""Tests for TextChunker and RAGService (no real DB required for unit tests)."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.gateway.services.rag import TextChunker, RAGService, _allowed_classifications


# ── TextChunker ───────────────────────────────────────────────────────────────

def test_chunker_empty_text():
    chunker = TextChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_chunker_short_text_single_chunk():
    chunker = TextChunker(chunk_size=100, overlap=10)
    text = "word " * 50
    chunks = chunker.chunk(text.strip())
    assert len(chunks) == 1
    assert chunks[0].startswith("word")


def test_chunker_produces_overlapping_chunks():
    chunker = TextChunker(chunk_size=4, overlap=2)
    words = ["a", "b", "c", "d", "e", "f", "g", "h"]
    text = " ".join(words)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    # Overlap: last 2 words of chunk 1 should appear at start of chunk 2
    first = chunks[0].split()
    second = chunks[1].split()
    assert first[-2:] == second[:2]


def test_chunker_exact_size_no_overlap():
    chunker = TextChunker(chunk_size=3, overlap=0)
    text = "a b c d e f"
    chunks = chunker.chunk(text)
    assert chunks == ["a b c", "d e f"]


def test_chunker_last_chunk_included():
    chunker = TextChunker(chunk_size=4, overlap=2)
    words = ["a", "b", "c", "d", "e"]
    chunks = chunker.chunk(" ".join(words))
    all_words = " ".join(chunks).split()
    for w in words:
        assert w in all_words


# ── _allowed_classifications ──────────────────────────────────────────────────

def test_allowed_classifications_public():
    allowed = _allowed_classifications("PUBLIC")
    assert allowed == {"PUBLIC"}


def test_allowed_classifications_internal():
    allowed = _allowed_classifications("INTERNAL")
    assert allowed == {"PUBLIC", "INTERNAL"}


def test_allowed_classifications_confidential():
    allowed = _allowed_classifications("CONFIDENTIAL")
    assert allowed == {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}


def test_allowed_classifications_restricted():
    allowed = _allowed_classifications("RESTRICTED")
    assert allowed == {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}


# ── RAGService.build_context ──────────────────────────────────────────────────

def test_build_context_empty():
    assert RAGService.build_context([]) == ""


def test_build_context_formats_numbered_sources():
    chunks = [
        {"content": "First chunk text", "similarity": 0.95},
        {"content": "Second chunk text", "similarity": 0.82},
    ]
    context = RAGService.build_context(chunks)
    assert "[Source 1]" in context
    assert "[Source 2]" in context
    assert "0.95" in context
    assert "First chunk text" in context
    assert "---" in context  # separator


# ── RAGService index_document ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_index_document_returns_chunk_count():
    trans_ctx = MagicMock()
    trans_ctx.__aenter__ = AsyncMock(return_value=None)
    trans_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=trans_ctx)

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_ctx

    fake_embedding = [0.1] * 768

    with patch(
        "src.gateway.services.rag.EmbeddingProviderFactory.get"
    ) as mock_factory:
        mock_embed_provider = AsyncMock()
        mock_embed_provider.embed = AsyncMock(return_value=[fake_embedding] * 3)
        mock_factory.return_value = mock_embed_provider

        svc = RAGService(db_pool=mock_pool)
        # 600 words → 2 chunks at default 400-word size with 50-word overlap
        long_text = " ".join([f"word{i}" for i in range(600)])
        count = await svc.index_document("doc-001", long_text, "INTERNAL", "default")

    assert count > 0
    assert mock_conn.execute.called


@pytest.mark.asyncio
async def test_index_document_empty_content():
    mock_pool = AsyncMock()
    svc = RAGService(db_pool=mock_pool)
    count = await svc.index_document("doc-002", "", "INTERNAL")
    assert count == 0


@pytest.mark.asyncio
async def test_retrieve_returns_chunks():
    fake_rows = [
        {"chunk_index": 0, "content": "relevant text", "data_class": "INTERNAL", "similarity": 0.91},
    ]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fake_rows)

    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = acquire_ctx

    fake_embedding = [0.2] * 768

    with patch(
        "src.gateway.services.rag.EmbeddingProviderFactory.get"
    ) as mock_factory:
        mock_embed_provider = AsyncMock()
        mock_embed_provider.embed = AsyncMock(return_value=[fake_embedding])
        mock_factory.return_value = mock_embed_provider

        svc = RAGService(db_pool=mock_pool)
        chunks = await svc.retrieve("what is relevant?", "default", "INTERNAL", top_k=5)

    assert len(chunks) == 1
    assert chunks[0]["content"] == "relevant text"
