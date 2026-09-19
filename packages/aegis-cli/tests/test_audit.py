"""Tests for `aegis audit` CLI commands (Phase 2)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from aegis_cli.main import app
from aegis_server.store.ledger import compute_hash

runner = CliRunner()

_INVENTORY_RECORD = {
    "seq": 1,
    "prev_hash": "genesis",
    "hash": "sha256:abc",
    "record_type": "model_inventory",
    "model_id": "default",
    "model_version": "sha256:test",
    "date_of_deployment": "2026-09-18T00:00:00+00:00",
    "model_risk_rating": "low",
    "model_owner": "team-a",
}

_RUN_EVIDENCE_RECORD = {
    "seq": 2,
    "prev_hash": "sha256:abc",
    "hash": "sha256:def",
    "record_type": "run_evidence",
    "model_id": "default",
    "run_id": "run-1",
    "status": "completed",
}


def _mock_client(
    ledger: list | None = None,
    inventory: list | None = None,
) -> MagicMock:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.list_ledger.return_value = ledger or []
    client.inventory_records.return_value = inventory or []
    return client


def test_audit_export_jsonl_stdout() -> None:
    records = [_INVENTORY_RECORD, _RUN_EVIDENCE_RECORD]
    mock = _mock_client(ledger=records)
    with patch("aegis_cli.commands.audit.AegisClient", return_value=mock):
        result = runner.invoke(app, ["audit", "export"])
    assert result.exit_code == 0
    lines = [ln for ln in result.output.strip().splitlines() if ln]
    assert len(lines) == 2
    assert json.loads(lines[0])["record_type"] == "model_inventory"
    assert json.loads(lines[1])["record_type"] == "run_evidence"


def test_audit_verify_valid_chain() -> None:
    """A correctly chained JSONL file passes verification."""
    r1: dict = {"seq": 1, "prev_hash": "genesis", "record_type": "test"}
    r1["hash"] = compute_hash(r1)

    r2: dict = {"seq": 2, "prev_hash": r1["hash"], "record_type": "test2"}
    r2["hash"] = compute_hash(r2)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(r1) + "\n")
        f.write(json.dumps(r2) + "\n")
        fname = f.name

    result = runner.invoke(app, ["audit", "verify", fname])
    assert result.exit_code == 0
    assert "OK" in result.output
    assert "2 record(s)" in result.output


def test_audit_verify_tampered_record_fails() -> None:
    """A tampered record causes verify to exit 1."""
    r1: dict = {"seq": 1, "prev_hash": "genesis", "record_type": "test"}
    r1["hash"] = compute_hash(r1)

    # Tamper after hashing
    r1_tampered = dict(r1)
    r1_tampered["record_type"] = "tampered"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(r1_tampered) + "\n")
        fname = f.name

    result = runner.invoke(app, ["audit", "verify", fname])
    assert result.exit_code == 1


def test_audit_inventory_table_output() -> None:
    records = [_INVENTORY_RECORD]
    mock = _mock_client(inventory=records)
    with patch("aegis_cli.commands.audit.AegisClient", return_value=mock):
        result = runner.invoke(app, ["audit", "inventory"])
    assert result.exit_code == 0
    assert "default" in result.output
    assert "team-a" in result.output


def test_audit_inventory_json_flag() -> None:
    records = [_INVENTORY_RECORD]
    mock = _mock_client(inventory=records)
    with patch("aegis_cli.commands.audit.AegisClient", return_value=mock):
        result = runner.invoke(app, ["audit", "inventory", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["model_id"] == "default"
