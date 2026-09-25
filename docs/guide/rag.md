# RAG

Retrieved documents are untrusted input, exactly like tool results. Aegis's
`RetrievalNode` pulls context from a vector store **and runs it through
tool-result guards before the model sees it**.

Install the extra first:

```bash
pip install "aegis-gateway-core[rag]"    # chromadb, langchain-chroma, langchain-postgres
```

## From the CLI

`aegis rag` indexes and queries a local, persistent Chroma store in
`~/.aegis/rag` — handy for trying retrieval and inspecting chunks:

```bash
aegis rag index ./handbook --glob "**/*.md" --namespace hr --chunk-size 1000
aegis rag query "How many vacation days do new hires get?" --namespace hr -k 4
```

::: warning Development embeddings
The CLI uses a deterministic fake embedder, so similarity is lexical at
best. Use it to exercise the plumbing, not to judge retrieval quality.
:::

## In a pipeline

```python
from aegis_core.mcp import ToolResultInjectionGuard
from aegis_core.pipeline import PipelineExecutor
from aegis_core.rag import RetrievalNode


def register_rag_route(executor: PipelineExecutor, provider, store, embedder) -> None:
    retrieval = RetrievalNode(
        store=store,  # any VectorStoreProvider
        embedder=embedder,  # any EmbeddingProvider
        namespace="hr",
        k=4,
        tool_result_guards=[ToolResultInjectionGuard()],
    )
    executor.register("hr", provider=provider, ingress=[retrieval])
```

Place the retrieval node in **ingress** so the context is in place when the
provider is called. It embeds the latest user message, queries the store,
drops any chunk a guard blocks, and appends the survivors as a single
`tool` message. Every per-chunk verdict is recorded in the run's events.

## Stores and embedders

| Contract | Methods | Shipped implementations |
|---|---|---|
| `VectorStoreProvider` | `add(docs, namespace)`, `query(vector, namespace, k)` | `ChromaVectorStore` (`aegis_core.rag.stores.chroma`), `PgVectorStore` (`aegis_core.rag.stores.pgvector`), `LangChainVectorStoreAdapter` for any LangChain vector store |
| `EmbeddingProvider` | `embed(texts)` | any `ModelProvider.embed`, or `FakeEmbeddingProvider` in tests |

Namespaces partition a store, so one Chroma or Postgres instance can serve
many routes.

## Over HTTP

When a server is built with a `rag_store` and `embedding_provider`,
`POST /v1/rag/index` and `POST /v1/rag/query` are live; otherwise they
return `503`. `aegis serve` does not configure a store yet — embed
`aegis_server.app.create_app(..., rag_store=..., embedding_provider=...)` in
your own entry point to enable them.
