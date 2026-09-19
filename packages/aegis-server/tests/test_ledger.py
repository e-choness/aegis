"""Tests for the evidence ledger (Phase 2).

Gate: DC uv run pytest packages/aegis-server -q -k ledger
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

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
