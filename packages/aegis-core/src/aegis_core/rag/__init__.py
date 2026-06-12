"""Aegis RAG — retrieval-augmented generation contracts and node (PROJECT_SPEC D3)."""

from aegis_core.rag.adapter import LangChainVectorStoreAdapter
from aegis_core.rag.chunker import TextChunker
from aegis_core.rag.protocol import Doc, EmbeddingProvider, VectorStoreProvider
from aegis_core.rag.retrieval_node import RetrievalNode

__all__ = [
    "Doc",
    "EmbeddingProvider",
    "LangChainVectorStoreAdapter",
    "RetrievalNode",
    "TextChunker",
    "VectorStoreProvider",
]
