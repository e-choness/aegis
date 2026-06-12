"""Tests for Step 12: RAG server endpoints — /v1/rag/index and /v1/rag/query.

Gate: DC uv run pytest packages/aegis-core packages/aegis-server -q -k rag
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_core.testing.rag import FakeEmbeddingProvider, FakeVectorStore
from aegis_server.app import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(
    rag_store: object | None = None,
    embedding_provider: object | None = None,
) -> TestClient:
    executor = PipelineExecutor()
    executor.register("default", provider=FakeProvider())
    app = create_app(
        executor=executor,
        no_auth=True,
        rag_store=rag_store,
        embedding_provider=embedding_provider,
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# No RAG configured — 503 guard
# ---------------------------------------------------------------------------


class TestRagNotConfigured:
    def test_index_returns_503_without_rag(self) -> None:
        client = _make_client()
        resp = client.post("/v1/rag/index", json={"documents": [{"text": "hi"}]})
        assert resp.status_code == 503

    def test_query_returns_503_without_rag(self) -> None:
        client = _make_client()
        resp = client.post("/v1/rag/query", json={"query": "hello"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Index endpoint
# ---------------------------------------------------------------------------


class TestRagIndexEndpoint:
    @pytest.fixture
    def client(self) -> TestClient:
        return _make_client(
            rag_store=FakeVectorStore(),
            embedding_provider=FakeEmbeddingProvider(),
        )

    def test_index_single_document(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/rag/index",
            json={"documents": [{"text": "hello world"}], "namespace": "default"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["indexed"] == 1
        assert data["namespace"] == "default"

    def test_index_multiple_documents(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/rag/index",
            json={
                "documents": [
                    {"text": "doc one"},
                    {"text": "doc two"},
                    {"text": "doc three"},
                ],
                "namespace": "multi",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["indexed"] == 3

    def test_index_with_metadata(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/rag/index",
            json={
                "documents": [{"text": "doc", "metadata": {"source": "test.txt"}}],
                "namespace": "meta",
            },
        )
        assert resp.status_code == 200

    def test_index_default_namespace(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/rag/index",
            json={"documents": [{"text": "no namespace specified"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["namespace"] == "default"

    def test_indexed_count_matches_documents(self, client: TestClient) -> None:
        docs = [{"text": f"doc {i}"} for i in range(7)]
        resp = client.post("/v1/rag/index", json={"documents": docs})
        assert resp.json()["indexed"] == 7


# ---------------------------------------------------------------------------
# Query endpoint
# ---------------------------------------------------------------------------


class TestRagQueryEndpoint:
    @pytest.fixture
    def store_and_embedder(self) -> tuple[FakeVectorStore, FakeEmbeddingProvider]:
        return FakeVectorStore(), FakeEmbeddingProvider()

    @pytest.fixture
    def client(self, store_and_embedder: tuple[FakeVectorStore, FakeEmbeddingProvider]) -> TestClient:
        store, embedder = store_and_embedder
        return _make_client(rag_store=store, embedding_provider=embedder)

    def test_query_returns_docs(
        self,
        client: TestClient,
        store_and_embedder: tuple[FakeVectorStore, FakeEmbeddingProvider],
    ) -> None:
        store, _ = store_and_embedder
        # Pre-populate the store directly
        import asyncio

        from aegis_core.rag.protocol import Doc
        asyncio.run(store.add([Doc(id="d1", text="Paris is the capital.")], "cities"))
        resp = client.post(
            "/v1/rag/query",
            json={"query": "capital of France", "namespace": "cities", "k": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["namespace"] == "cities"
        assert len(data["docs"]) == 1
        assert data["docs"][0]["text"] == "Paris is the capital."

    def test_query_default_namespace(self, client: TestClient) -> None:
        resp = client.post("/v1/rag/query", json={"query": "something"})
        assert resp.status_code == 200
        assert resp.json()["namespace"] == "default"

    def test_query_empty_namespace_returns_empty_docs(self, client: TestClient) -> None:
        resp = client.post("/v1/rag/query", json={"query": "nothing here", "namespace": "empty_ns"})
        assert resp.status_code == 200
        assert resp.json()["docs"] == []

    def test_query_response_structure(self, client: TestClient) -> None:
        resp = client.post("/v1/rag/query", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "docs" in data
        assert "namespace" in data

    def test_index_then_query_round_trip(self, client: TestClient) -> None:
        # Index via HTTP
        client.post(
            "/v1/rag/index",
            json={"documents": [{"text": "London is in England."}], "namespace": "geo"},
        )
        # Query via HTTP
        resp = client.post(
            "/v1/rag/query",
            json={"query": "where is London", "namespace": "geo", "k": 1},
        )
        assert resp.status_code == 200
        docs = resp.json()["docs"]
        assert len(docs) == 1
        assert "London" in docs[0]["text"]
