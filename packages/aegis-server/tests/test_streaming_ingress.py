"""Regression tests: streamed chat requests must be governed like every other request.

Previously a ``stream: true`` request on a true-streaming route called the
provider directly — ingress nodes never ran and the run was never recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import ClassVar, Literal

from starlette.testclient import TestClient

from aegis_core.guardrails import GuardNode
from aegis_core.pipeline import PipelineAssembler
from aegis_core.pipeline.assembler import StreamCapability
from aegis_core.pipeline.checkpointer import make_memory_checkpointer
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.pipeline.verdict import Verdict
from aegis_core.providers.models import Message
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.store.ledger import InMemoryLedgerStore


class _AllowIncremental:
    name = "allow_incremental"
    streaming: ClassVar[Literal["none", "incremental"]] = "incremental"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.allow()

    async def scan_chunk(self, chunk: str) -> Verdict:
        return Verdict.allow()

    async def finalize(self, accumulated: str) -> Verdict:
        return Verdict.allow()


class _BlockEverything:
    name = "block_everything"
    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.block("ingress policy says no")


class _NeedsApproval:
    name = "needs_approval"
    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.require_approval("a human must look at this")


@dataclass
class _MaskSecret:
    """Stand-in for the PII mask node: rewrites messages on ingress."""

    name: str = "mask_secret"

    async def run(self, state: RunState) -> RunStateDelta:
        masked = [Message(role=m.role, content=m.content.replace("hunter2", "<SECRET_0>")) for m in state.messages]
        return RunStateDelta(messages=masked, mask_map={"<SECRET_0>": "hunter2"})


@dataclass
class _Unmask:
    """An egress transformation node that doesn't declare stream_capability."""

    name: str = "unmask"

    async def run(self, state: RunState) -> RunStateDelta:
        return RunStateDelta(response=(state.response or "").replace("<SECRET_0>", "hunter2"))


def _client(ingress: list, *, checkpointer: object | None = None) -> tuple[TestClient, FakeProvider]:
    fake = FakeProvider(stream_chunks=["hello", " world"])
    executor = PipelineExecutor(checkpointer=checkpointer)
    executor.register(
        "default",
        provider=fake,
        ingress=ingress,
        egress=[GuardNode([_AllowIncremental()], name="egress")],
    )
    assert executor.get("default").stream_capability == StreamCapability.TRUE_STREAMING
    app = create_app(executor, no_auth=True, ledger_store=InMemoryLedgerStore())
    return TestClient(app), fake


def _stream(client: TestClient, content: str = "hi") -> list[dict]:
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "default", "messages": [{"role": "user", "content": content}], "stream": True},
    )
    assert resp.status_code == 200
    frames = []
    for line in resp.text.splitlines():
        if line.startswith("data: ") and line[6:].strip() != "[DONE]":
            frames.append(json.loads(line[6:]))
    return frames


def test_ingress_block_stops_true_stream_before_provider() -> None:
    client, fake = _client([GuardNode([_BlockEverything()], name="policy")])

    frames = _stream(client)

    assert fake.stream_calls == []
    assert fake.complete_calls == []
    assert frames[-1]["choices"][0]["finish_reason"] == "content_filter"
    assert frames[-1]["aegis_event"] == "blocked"

    runs = client.get("/v1/audit").json()["runs"]
    assert [r["status"] for r in runs] == ["blocked"]
    ledger = client.get("/v1/audit/ledger").json()["records"]
    assert ledger[-1]["status"] == "blocked"
    assert any(e["event_type"] == "verdict" for e in ledger[-1]["events"])


def test_provider_streams_ingress_processed_messages() -> None:
    client, fake = _client([_MaskSecret()])

    frames = _stream(client, "my password is hunter2")

    assert len(fake.stream_calls) == 1
    sent = fake.stream_calls[0].messages[-1].content
    assert "hunter2" not in sent
    assert "<SECRET_0>" in sent
    assert frames[-1]["choices"][0]["finish_reason"] == "stop"
    assert client.get("/v1/audit").json()["runs"][0]["status"] == "completed"


def test_ingress_pause_on_stream_is_checkpointed_and_resumable() -> None:
    client, fake = _client([GuardNode([_NeedsApproval()], name="review")], checkpointer=make_memory_checkpointer())

    frames = _stream(client)

    assert fake.stream_calls == []
    held = frames[-1]
    assert held["aegis_event"] == "paused"
    run_id = held["aegis_run_id"]
    assert client.get(f"/v1/runs/{run_id}").json()["status"] == "paused"

    resumed = client.post(f"/v1/runs/{run_id}/resume", json={"decision": "denied"})
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "denied"


def test_non_streaming_blocked_chat_is_recorded_as_blocked() -> None:
    client, fake = _client([GuardNode([_BlockEverything()], name="policy")])

    resp = client.post(
        "/v1/chat/completions",
        json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.json()["choices"][0]["finish_reason"] == "content_filter"
    assert fake.complete_calls == []
    ledger = client.get("/v1/audit/ledger").json()["records"]
    assert ledger[-1]["status"] == "blocked"


def test_undeclared_egress_node_forces_buffering() -> None:
    """A transformation node on egress must see the full response, so the route buffers."""
    pipeline = PipelineAssembler().compile(provider=FakeProvider(), egress=[_Unmask()])
    assert pipeline.stream_capability == StreamCapability.BUFFERED


def test_models_endpoint_lists_routes() -> None:
    client, _ = _client([])
    body = client.get("/v1/models").json()
    assert body["object"] == "list"
    assert [m["id"] for m in body["data"]] == ["default"]
