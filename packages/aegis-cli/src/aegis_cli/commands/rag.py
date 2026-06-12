"""aegis rag — index documents and query the local RAG vector store.

Uses a persistent Chroma store at ``~/.aegis/rag/`` and a deterministic
fake embedding provider so that index → query round trips work across
separate process invocations without a real embedding API.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="RAG: index documents and query the vector store.")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_store_and_embedder() -> tuple[Any, Any]:
    """Build a persistent Chroma store + deterministic embedder for CLI use."""
    import chromadb

    from aegis_core.rag.adapter import LangChainVectorStoreAdapter
    from aegis_core.rag.chroma_store import make_chroma_store_factory
    from aegis_core.testing.rag import FakeEmbeddingProvider

    rag_dir = Path.home() / ".aegis" / "rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(rag_dir))

    fake_emb = FakeEmbeddingProvider()
    factory = make_chroma_store_factory(
        client=client,
        embedding_function=fake_emb.as_langchain_embeddings(),
    )
    store = LangChainVectorStoreAdapter(store_factory=factory)
    return store, fake_emb


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("index")
def index_docs(
    path: Path = typer.Argument(..., help="Directory containing files to index."),  # noqa: B008
    namespace: str = typer.Option("default", "--namespace", "-n", help="Target namespace."),
    chunk_size: int = typer.Option(1000, "--chunk-size", help="Characters per chunk."),
    chunk_overlap: int = typer.Option(
        200, "--chunk-overlap", help="Overlap characters between chunks."
    ),
    glob: str = typer.Option("**/*.txt", "--glob", help="File glob pattern."),
) -> None:
    """Index all matching files in PATH into the RAG vector store."""
    from aegis_core.rag.chunking import chunk_text
    from aegis_core.rag.protocol import Doc

    files = list(path.glob(glob))
    if not files:
        typer.echo(f"No files matching '{glob}' found in {path}.")
        raise typer.Exit(1)

    store, _ = _make_store_and_embedder()

    async def _run() -> None:
        all_docs: list[Doc] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                typer.echo(f"  skipping {f}: {exc}", err=True)
                continue
            chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for chunk in chunks:
                all_docs.append(Doc(text=chunk, metadata={"source": str(f)}))

        if not all_docs:
            typer.echo("No text chunks produced — nothing indexed.")
            return

        await store.add(all_docs, namespace)
        typer.echo(
            f"Indexed {len(all_docs)} chunk(s) from {len(files)} file(s)"
            f" into namespace '{namespace}'."
        )

    asyncio.run(_run())


@app.command("query")
def query_docs(
    query: str = typer.Argument(..., help="Query text."),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Namespace to query."),
    k: int = typer.Option(4, "--k", "-k", help="Maximum results."),
    json_output: bool = typer.Option(False, "--json", is_flag=True, help="Emit JSON."),
) -> None:
    """Query the RAG vector store and print matching chunks."""
    store, embedder = _make_store_and_embedder()

    async def _run() -> None:
        vectors = await embedder.embed([query])
        docs = await store.query(vectors[0], namespace, k)

        if not docs:
            typer.echo("No results found.")
            return

        if json_output:
            typer.echo(
                json.dumps([{"text": d.text, "metadata": d.metadata} for d in docs])
            )
        else:
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get("source", "")
                snippet = doc.text[:300].replace("\n", " ")
                typer.echo(f"\n[{i}] {source}\n{snippet}")

    asyncio.run(_run())
