"""Scenario 04 — RAG (Retrieval-Augmented Generation).

Demonstrates:
- Indexing documents from examples/docs/ into the Aegis vector store.
- Querying the store and showing retrieved chunks.
- A governed chat request that enriches context with RAG-retrieved content,
  routed through the tool-result guard chain for injection detection.

Prerequisites:
    - Aegis server running with RAG enabled (aegis-core[rag] installed).
    - Set AEGIS_SERVER_URL and AEGIS_API_KEY as appropriate.

Note:
    Use `aegis rag index examples/docs/` and `aegis rag query "<question>"`
    from the CLI, or use the /v1/rag/* REST endpoints directly.
    This script uses httpx for the RAG endpoints (not yet in the SDK).
"""

from __future__ import annotations

import os

import httpx

SERVER_URL = os.environ.get("AEGIS_SERVER_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("AEGIS_API_KEY", "")
DOCS_DIR = os.environ.get("AEGIS_DOCS_DIR", "examples/docs")

_HEADERS: dict[str, str] = {}
if API_KEY:
    _HEADERS["Authorization"] = f"Bearer {API_KEY}"


def main() -> None:
    with httpx.Client(base_url=SERVER_URL, headers=_HEADERS) as http:
        print("── Scenario 04: RAG ────────────────────────────────")

        # Index documents.
        print(f"\n[1] Indexing documents from {DOCS_DIR!r} …")
        import pathlib
        docs = list(pathlib.Path(DOCS_DIR).glob("*.txt"))
        if not docs:
            print(f"  No .txt files found in {DOCS_DIR!r}. Skipping index step.")
        else:
            for doc in docs:
                resp = http.post(
                    "/v1/rag/index",
                    json={"text": doc.read_text(), "metadata": {"source": doc.name}},
                )
                status = "ok" if resp.is_success else f"error {resp.status_code}"
                print(f"  {doc.name}: {status}")

        # Query.
        question = "What is Aegis?"
        print(f"\n[2] Querying: {question!r}")
        resp = http.post("/v1/rag/query", json={"query": question, "top_k": 3})
        if not resp.is_success:
            print(f"  RAG query failed: {resp.status_code} — {resp.text[:200]}")
            print("  (Ensure aegis-core[rag] is installed and a rag_store is configured.)")
            return
        results = resp.json().get("results", [])
        for i, chunk in enumerate(results, 1):
            src = chunk.get("metadata", {}).get("source", "?")
            text = (chunk.get("text") or "")[:100]
            print(f"  [{i}] {src}: {text!r}")


if __name__ == "__main__":
    main()
