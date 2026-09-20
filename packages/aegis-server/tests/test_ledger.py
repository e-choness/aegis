"""Tests for the evidence ledger (Phase 2).

Gate: DC uv run pytest packages/aegis-server -q -k ledger
"""

from __future__ import annotations

import json
import pathlib
from typing import ClassVar, Literal

import httpx
import pytest
from starlette.testclient import TestClient

from aegis_core.guardrails import GuardNode
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.pipeline.verdict import Verdict
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.ledger import (
    InMemoryLedgerStore,
    compute_hash,
    redact_events,
)

# ---------------------------------------------------------------------------
# Unit tests — InMemoryLedgerStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inmemory_append_sets_seq_and_hash_chain() -> None:
    store = InMemoryLedgerStore()
    r1 = await store.append(None, {"record_type": "model_inventory", "model_id": "default"})
    r2 = await store.append("run-1", {"record_type": "run_evidence", "run_id": "run-1"})

    assert r1["seq"] == 1
    assert r1["prev_hash"] == "genesis"
    assert r1["hash"].startswith("sha256:")

    assert r2["seq"] == 2
    assert r2["prev_hash"] == r1["hash"]


@pytest.mark.asyncio
async def test_inmemory_hash_is_reproducible() -> None:
    store = InMemoryLedgerStore()
    r1 = await store.append(None, {"record_type": "test", "val": 42})
    without_hash = {k: v for k, v in r1.items() if k != "hash"}
    assert r1["hash"] == compute_hash(without_hash)


@pytest.mark.asyncio
async def test_inmemory_list_records_since_seq() -> None:
    store = InMemoryLedgerStore()
    await store.append(None, {"record_type": "a"})
    await store.append(None, {"record_type": "b"})
    await store.append(None, {"record_type": "c"})

    all_recs = await store.list_records(since_seq=0)
    assert len(all_recs) == 3

    after_first = await store.list_records(since_seq=1)
    assert len(after_first) == 2
    assert after_first[0]["record_type"] == "b"


# ---------------------------------------------------------------------------
# Integration tests — ledger API endpoints via client_with_ledger fixture
# ---------------------------------------------------------------------------


def test_audit_ledger_contains_inventory_on_startup(client_with_ledger: TestClient) -> None:
    """Lifespan emits model_inventory records visible via GET /v1/audit/ledger."""
    resp = client_with_ledger.get("/v1/audit/ledger")
    assert resp.status_code == 200
    records = resp.json()["records"]
    inv = [r for r in records if r.get("record_type") == "model_inventory"]
    assert len(inv) >= 1
    assert inv[0]["model_id"] == "default"
    assert inv[0]["hash"].startswith("sha256:")


def test_audit_ledger_after_run_has_run_evidence(client_with_ledger: TestClient) -> None:
    """After POST /v1/runs the ledger gains a run_evidence record."""
    client_with_ledger.post(
        "/v1/runs",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    resp = client_with_ledger.get("/v1/audit/ledger")
    records = resp.json()["records"]
    run_ev = [r for r in records if r.get("record_type") == "run_evidence"]
    assert len(run_ev) == 1
    assert run_ev[0]["model_id"] == "default"
    assert run_ev[0]["hash"].startswith("sha256:")


def test_audit_inventory_returns_only_inventory_records(client_with_ledger: TestClient) -> None:
    """GET /v1/audit/inventory returns only model_inventory records."""
    client_with_ledger.post(
        "/v1/runs",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    resp = client_with_ledger.get("/v1/audit/inventory")
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert records  # at least one inventory record from lifespan
    assert all(r.get("record_type") == "model_inventory" for r in records)


def test_audit_ledger_since_seq_filter(client_with_ledger: TestClient) -> None:
    """?since_seq=N returns only records with seq > N."""
    # POST two runs to get two run_evidence records after the inventory
    client_with_ledger.post("/v1/runs", json={"messages": [{"role": "user", "content": "a"}]})
    client_with_ledger.post("/v1/runs", json={"messages": [{"role": "user", "content": "b"}]})

    all_records = client_with_ledger.get("/v1/audit/ledger").json()["records"]
    assert len(all_records) >= 2

    # Filter from the last record seq — expect empty
    last_seq = all_records[-1]["seq"]
    resp = client_with_ledger.get(f"/v1/audit/ledger?since_seq={last_seq}")
    assert resp.json()["records"] == []


# ---------------------------------------------------------------------------
# Unit test — redact_events
# ---------------------------------------------------------------------------


def test_redact_events_strips_mask_map_and_messages() -> None:
    events = [
        {
            "event_type": "pii",
            "data": {"mask_map": {"Alice": "PERSON_1"}, "count": 1, "messages": ["hi"]},
        },
        {"event_type": "verdict", "data": {"kind": "block"}},
    ]
    redacted = redact_events(events)
    assert "mask_map" not in redacted[0]["data"]
    assert "messages" not in redacted[0]["data"]
    assert redacted[0]["data"]["count"] == 1
    assert redacted[1]["data"]["kind"] == "block"


# ---------------------------------------------------------------------------
# Integration — mask_map never reaches the ledger via a real pipeline run
# ---------------------------------------------------------------------------


class _FakePiiNode:
    """Minimal PipelineNode emitting a pii-shaped verdict event with mask_map/messages."""

    name = "pii.mask"

    async def run(self, state: RunState) -> RunStateDelta:
        return RunStateDelta(
            events=[
                RunEvent(
                    stage="ingress",
                    node="pii.mask",
                    event_type="verdict",
                    data={
                        "verdict": "sanitize",
                        "entities": {"EMAIL_ADDRESS": 1},
                        "mask_map": {"<EMAIL_ADDRESS_1>": "a@b.com"},
                        "messages": ["my email is a@b.com"],
                    },
                )
            ]
        )


def test_mask_map_never_in_ledger() -> None:
    """A run that emits a PII mask_map in its events never persists it to the ledger."""
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake, ingress=[_FakePiiNode()])
    ledger = InMemoryLedgerStore()
    app = create_app(ex, no_auth=True, ledger_store=ledger)

    with TestClient(app, raise_server_exceptions=True) as client:
        client.post("/v1/runs", json={"messages": [{"role": "user", "content": "my email is a@b.com"}]})
        records = client.get("/v1/audit/ledger").json()["records"]

    run_ev = [r for r in records if r.get("record_type") == "run_evidence"]
    assert len(run_ev) == 1
    verdict_events = [e for e in run_ev[0]["events"] if e["event_type"] == "verdict"]
    assert len(verdict_events) == 1
    ev_data = verdict_events[0]["data"]
    assert "mask_map" not in ev_data
    assert "messages" not in ev_data
    assert ev_data["entities"] == {"EMAIL_ADDRESS": 1}
    # Guard against a redaction bug being masked by dict re-serialisation.
    assert "a@b.com" not in json.dumps(run_ev[0])


# ---------------------------------------------------------------------------
# Integration — inventory record on startup and on config digest change
# ---------------------------------------------------------------------------


def test_inventory_record_emitted_on_start_and_on_digest_change() -> None:
    """A fresh server start with a different config digest appends a new inventory record."""
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ledger = InMemoryLedgerStore()

    app1 = create_app(ex, no_auth=True, ledger_store=ledger, config_digest="sha256:aaa")
    with TestClient(app1, raise_server_exceptions=True):
        pass

    app2 = create_app(ex, no_auth=True, ledger_store=ledger, config_digest="sha256:bbb")
    with TestClient(app2, raise_server_exceptions=True):
        pass

    inv = [r for r in ledger._records if r["record_type"] == "model_inventory"]
    assert len(inv) == 2
    assert {r["model_version"] for r in inv} == {"sha256:aaa", "sha256:bbb"}


# ---------------------------------------------------------------------------
# Integration — HITL denial records the approver's identity in the ledger
# ---------------------------------------------------------------------------


class _ApprovalGuard:
    """Always returns require_approval to trigger HITL pause."""

    name = "approval_guard"
    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    async def scan(self, state: RunState) -> Verdict:
        return Verdict.require_approval("human review required")


def test_hitl_denial_records_approver_identity() -> None:
    """A denied HITL run's ledger record carries the approver's identity and decision."""
    from aegis_core.pipeline.checkpointer import make_memory_checkpointer

    ks = KeyStore()
    api_key = ks.create(principal_id="jane", team="compliance")
    fake = FakeProvider(complete_response="should not be reached")
    ex = PipelineExecutor(checkpointer=make_memory_checkpointer())
    ex.register(
        "default",
        provider=fake,
        ingress=[GuardNode(guards=[_ApprovalGuard()], name="approval")],
    )
    ledger = InMemoryLedgerStore()
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), ledger_store=ledger)

    with TestClient(app, raise_server_exceptions=True) as client:
        run_resp = client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        run_id = run_resp.json()["run_id"]
        assert run_resp.json()["status"] == "paused"

        resume_resp = client.post(
            f"/v1/runs/{run_id}/resume",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"decision": "denied"},
        )
        assert resume_resp.json()["status"] == "denied"

        records = client.get(
            "/v1/audit/ledger", headers={"Authorization": f"Bearer {api_key}"}
        ).json()["records"]

    run_ev = [r for r in records if r.get("record_type") == "run_evidence" and r.get("run_id") == run_id]
    # One record from the initial pause, one from the resume decision.
    assert len(run_ev) == 2
    resolved = run_ev[-1]
    assert resolved["status"] == "denied"
    assert resolved["approver"] == {
        "principal_id": "jane",
        "decision": "denied",
        "at": resolved["approver"]["at"],
    }


# ---------------------------------------------------------------------------
# Integration — background runs also append to the ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_background_run_appends_to_ledger() -> None:
    import asyncio

    fake = FakeProvider(complete_response="background result")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ledger = InMemoryLedgerStore()
    app = create_app(ex, no_auth=True, ledger_store=ledger)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/v1/runs",
            json={"messages": [{"role": "user", "content": "hi"}], "background": True},
        )
        run_id = resp.json()["run_id"]
        assert resp.json()["status"] == "pending"

        await asyncio.sleep(0.1)
        records = (await client.get("/v1/audit/ledger")).json()["records"]

    run_ev = [r for r in records if r.get("record_type") == "run_evidence" and r.get("run_id") == run_id]
    assert len(run_ev) == 1
    assert run_ev[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Integration — the full evidence chain verifies after many runs
# ---------------------------------------------------------------------------


def test_chain_verifies_after_n_runs() -> None:
    n = 50
    fake = FakeProvider(complete_response="ok")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ledger = InMemoryLedgerStore()
    app = create_app(ex, no_auth=True, ledger_store=ledger)

    with TestClient(app, raise_server_exceptions=True) as client:
        for i in range(n):
            resp = client.post("/v1/runs", json={"messages": [{"role": "user", "content": f"msg {i}"}]})
            assert resp.status_code == 200
        records = client.get("/v1/audit/ledger").json()["records"]

    assert len(records) == n + 1  # + 1 startup inventory record
    prev_hash = "genesis"
    for record in records:
        assert record["prev_hash"] == prev_hash
        without_hash = {k: v for k, v in record.items() if k != "hash"}
        assert record["hash"] == compute_hash(without_hash)
        prev_hash = record["hash"]


# ---------------------------------------------------------------------------
# Integration — export validates against the published JSON Schema
# ---------------------------------------------------------------------------


def test_export_validates_against_schema(client_with_ledger: TestClient) -> None:
    jsonschema = pytest.importorskip("jsonschema")

    client_with_ledger.post("/v1/runs", json={"messages": [{"role": "user", "content": "hi"}]})
    records = client_with_ledger.get("/v1/audit/ledger").json()["records"]
    assert records

    schema_path = (
        pathlib.Path(__file__).resolve().parents[3] / "docs" / "assets" / "evidence-record.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    for record in records:
        validator.validate(record)
