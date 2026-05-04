from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/rag")


class IndexRequest(BaseModel):
    document_id: str
    content: str
    data_classification: str = "INTERNAL"
    namespace: str = "default"


class IndexResponse(BaseModel):
    document_id: str
    chunks_indexed: int


class QueryRequest(BaseModel):
    question: str
    namespace: str = "default"
    data_classification: str = "INTERNAL"
    top_k: int = 5


class QueryResponse(BaseModel):
    context: str
    chunks: list[dict]
    chunk_count: int


def _rag(request: Request):
    svc = getattr(request.app.state, "rag_service", None)
    if svc is None:
        raise HTTPException(503, "RAG service not configured (VECTORDB_URL not set)")
    return svc


@router.post("/index", response_model=IndexResponse, status_code=201)
async def index_document(body: IndexRequest, rag=Depends(_rag)):
    chunks_indexed = await rag.index_document(
        document_id=body.document_id,
        content=body.content,
        data_classification=body.data_classification,
        namespace=body.namespace,
    )
    return IndexResponse(document_id=body.document_id, chunks_indexed=chunks_indexed)


@router.post("/query", response_model=QueryResponse)
async def query_rag(body: QueryRequest, rag=Depends(_rag)):
    chunks = await rag.retrieve(
        query=body.question,
        namespace=body.namespace,
        data_classification=body.data_classification,
        top_k=body.top_k,
    )
    from ...services.rag import RAGService
    context = RAGService.build_context(chunks)
    return QueryResponse(context=context, chunks=chunks, chunk_count=len(chunks))
