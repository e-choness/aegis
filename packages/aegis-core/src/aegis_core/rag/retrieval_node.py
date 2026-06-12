"""RetrievalNode — PipelineNode that retrieves context and guards results.

Implements PROJECT_SPEC D13: "RAG-retrieved content flows through the
tool-result chain."

Execution order:
    1. Embed the last user message.
    2. Query the VectorStoreProvider for similar docs.
    3. Pass each doc text through every ToolResultGuard.
    4. Inject passing docs as a ``role="tool"`` context message.
"""

from __future__ import annotations

from aegis_core.mcp.protocol import ToolResultGuard
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.providers.models import Message
from aegis_core.rag.protocol import EmbeddingProvider, VectorStoreProvider


class RetrievalNode:
    """Retrieval-augmented-generation pipeline node.

    Place this in the *ingress* list of
    :class:`~aegis_core.pipeline.assembler.PipelineAssembler` so that
    retrieved context is available when the execute node calls the model.

    Args:
        store: Vector store to query.
        embedder: Embedding provider for the user query.
        namespace: Collection name to query.
        k: Number of docs to retrieve.
        tool_result_guards: Guards applied to each retrieved doc (injection
            scan).  Any ``block`` verdict drops that doc from the context.
        name: Node identifier shown in run events.
    """

    def __init__(
        self,
        store: VectorStoreProvider,
        embedder: EmbeddingProvider,
        namespace: str = "default",
        k: int = 4,
        tool_result_guards: list[ToolResultGuard] | None = None,
        name: str = "retrieval",
    ) -> None:
        self.name = name
        self._store = store
        self._embedder = embedder
        self._namespace = namespace
        self._k = k
        self._tool_result_guards: list[ToolResultGuard] = tool_result_guards or []

    async def run(self, state: RunState) -> RunStateDelta:
        """Retrieve context, run guards, inject passing docs into messages."""
        events: list[RunEvent] = []

        # ── 1. Find last user message as query ────────────────────────────
        query = ""
        for msg in reversed(state.messages):
            if msg.role == "user":
                query = msg.content
                break
        if not query:
            return RunStateDelta(events=events)

        # ── 2. Embed query ────────────────────────────────────────────────
        [vector] = await self._embedder.embed([query])

        # ── 3. Query vector store ──────────────────────────────────────────
        docs = await self._store.query(vector, self._namespace, self._k)

        # ── 4. Guard each doc ─────────────────────────────────────────────
        passing_texts: list[str] = []
        for doc in docs:
            blocked = False
            for guard in self._tool_result_guards:
                verdict = await guard.scan_result("rag_retrieval", doc.text, state)
                events.append(
                    RunEvent(
                        stage="retrieval_guard",
                        node=guard.name,
                        event_type="verdict",
                        data={
                            "verdict": verdict.kind.value,
                            "doc_id": doc.id,
                            "reason": verdict.reason,
                        },
                    )
                )
                if verdict.is_block:
                    blocked = True
                    break
            if not blocked:
                passing_texts.append(doc.text)

        # ── 5. Inject context ─────────────────────────────────────────────
        if not passing_texts:
            return RunStateDelta(events=events)

        context = "\n\n".join(
            f"[Context {i + 1}]: {text}" for i, text in enumerate(passing_texts)
        )
        new_messages = [*state.messages, Message(role="tool", content=context)]
        return RunStateDelta(messages=new_messages, events=events)
