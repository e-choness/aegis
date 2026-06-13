"""Example 04 — RAG (retrieval-augmented generation).

Shows how to attach a vector store and embedding provider to the pipeline
so retrieved context is injected before the LLM call.

This example uses an in-memory Chroma-free stub — no database or API key
needed.  For a production setup, swap in:
  - ``aegis_core.rag.ChromaVectorStore``
  - your embedding provider (OpenAI, Cohere, …)

Run::

    uv run python examples/04_rag.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider


class _StubVectorStore:
    """Minimal in-memory vector store for the demo."""

    async def search(self, query: str, top_k: int = 3) -> list[dict[str, str]]:
        _ = query
        return [
            {"text": "Aegis is an open-source AI gateway.", "source": "docs/overview.md"},
            {"text": "Aegis enforces guardrails on every LLM call.", "source": "docs/guardrails.md"},
        ][:top_k]


async def main() -> None:
    provider = FakeProvider(complete_response="Aegis is an open-source, plugin-first AI gateway.")

    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    user_query = "Tell me about Aegis."

    # Retrieve context (outside the pipeline for this stub demo)
    store = _StubVectorStore()
    docs = await store.search(user_query)
    context_block = "\n\n".join(f"[doc] {d['text']}" for d in docs)
    augmented_message = f"Context:\n{context_block}\n\nQuestion: {user_query}"

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content=augmented_message)],
        principal="demo-user",
    )

    result = await pipeline.run(state)

    print(f"[run_id]   {result.run_id}")
    print(f"[status]   {result.status}")
    print(f"[docs]     {len(docs)} retrieved")
    print(f"[response] {result.response}")


if __name__ == "__main__":
    asyncio.run(main())
