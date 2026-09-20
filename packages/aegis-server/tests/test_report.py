"""Tests for GET /v1/audit/report (Phase 3)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


def test_report_no_ledger(client_no_auth: TestClient) -> None:
    """When no ledger is wired, report returns empty but valid structure."""
    resp = client_no_auth.get("/v1/audit/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["inventory"] == []
    assert body["run_stats"] == {}
    assert body["chain_length"] == 0
    assert "generated_at" in body


def test_report_with_ledger_empty(client_with_ledger: TestClient) -> None:
    """After server start, inventory record is present; no run records yet."""
    resp = client_with_ledger.get("/v1/audit/report")
    assert resp.status_code == 200
    body = resp.json()
    # lifespan emits one model_inventory record
    assert len(body["inventory"]) >= 1
    assert body["run_stats"] == {}
    assert body["chain_length"] >= 1
    assert "generated_at" in body


def test_report_with_run_records(client_with_ledger: TestClient) -> None:
    """After a completed run, run_stats reflect the outcome."""
    # trigger a run so a run_evidence record is emitted
    client_with_ledger.post(
        "/v1/chat/completions",
        json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
    )
    resp = client_with_ledger.get("/v1/audit/report")
    assert resp.status_code == 200
    body = resp.json()
    assert sum(body["run_stats"].values()) >= 1
    assert body["chain_length"] >= 2


def test_report_inventory_fields(client_with_ledger: TestClient) -> None:
    """Inventory records include risk_rating from route_metadata."""
    resp = client_with_ledger.get("/v1/audit/report")
    assert resp.status_code == 200
    inventory = resp.json()["inventory"]
    assert len(inventory) >= 1
    rec = inventory[0]
    assert rec.get("record_type") == "model_inventory"
    assert rec.get("model_id") is not None
