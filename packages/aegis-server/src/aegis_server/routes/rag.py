"""RAG HTTP endpoints — /v1/rag/index and /v1/rag/query (PROJECT_SPEC D3)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aegis_core.rag.protocol import Doc

router = APIRouter(tags=["rag"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class IndexDocumentInput(BaseModel):
    text: str
    metadata: dict[str, Any] = {}


class IndexRequest(BaseModel):
    documents: list[IndexDocumentInput]
    namespace: str = "default"


class IndexResponse(BaseModel):
    indexed: int
    namespace: str


class QueryRequest(BaseModel):
    query: str
    namespace: str = "default"
    k: int = 4


class DocResponse(BaseModel):
    id: str | None
    text: str
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    docs: list[DocResponse]
    namespace: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_rag(request: Request) -> tuple[Any, Any]:
    """Return (rag_store, embedding_provider) from app.state or raise 503."""
    rag_store = getattr(request.app.state, "rag_store", None)
    embedding_provider = getattr(request.app.state, "embedding_provider", None)
    if rag_store is None or embedding_provider is None:
        raise HTTPException(status_code=503, detail="RAG not configured on this server.")
    return rag_store, embedding_provider


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/v1/rag/index", response_model=IndexResponse)
async def rag_index(body: IndexRequest, request: Request) -> IndexResponse:
    """Index documents into a namespace."""
    rag_store, _embedding_provider = _get_rag(request)
    docs = [
        Doc(id=str(uuid.uuid4()), text=d.text, metadata=d.metadata)
        for d in body.documents
    ]
    await rag_store.add(docs, body.namespace)
    return IndexResponse(indexed=len(docs), namespace=body.namespace)


@router.post("/v1/rag/query", response_model=QueryResponse)
async def rag_query(body: QueryRequest, request: Request) -> QueryResponse:
    """Query a namespace and return the *k* most similar documents."""
    rag_store, embedding_provider = _get_rag(request)
    [vector] = await embedding_provider.embed([body.query])
    docs = await rag_store.query(vector, body.namespace, body.k)
    return QueryResponse(
        docs=[DocResponse(id=d.id, text=d.text, metadata=d.metadata) for d in docs],
        namespace=body.namespace,
    )
