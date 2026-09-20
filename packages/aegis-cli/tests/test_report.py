"""Tests for `aegis report` CLI commands (Phase 3)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from aegis_cli.main import app

runner = CliRunner()

_REPORT = {
    "generated_at": "2026-09-18T00:00:00+00:00",
    "inventory": [
        {
            "seq": 1,
            "record_type": "model_inventory",
            "model_id": "default",
            "model_version": "sha256:test",
            "date_of_deployment": "2026-09-18T00:00:00+00:00",
            "model_risk_rating": "low",
            "model_owner": "team-a",
        }
    ],
    "run_stats": {"completed": 3, "blocked": 1},
    "chain_length": 5,
}


def _mock_client(report: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.audit_report.return_value = report or _REPORT
    return client


def test_report_summary_table() -> None:
    """Default output renders a human-readable table."""
    mock = _mock_client()
    with patch("aegis_cli.commands.report.AegisClient", return_value=mock):
        result = runner.invoke(app, ["report", "summary"])
    assert result.exit_code == 0
    assert "default" in result.output
    assert "low" in result.output
    assert "completed" in result.output
    assert "chain length: 5" in result.output


def test_report_summary_json() -> None:
    """--json flag emits raw JSON."""
    mock = _mock_client()
    with patch("aegis_cli.commands.report.AegisClient", return_value=mock):
        result = runner.invoke(app, ["report", "summary", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["chain_length"] == 5
    assert len(data["inventory"]) == 1


def test_report_summary_empty_inventory() -> None:
    """Empty inventory prints a placeholder message."""
    report = {**_REPORT, "inventory": [], "run_stats": {}, "chain_length": 0}
    mock = _mock_client(report=report)
    with patch("aegis_cli.commands.report.AegisClient", return_value=mock):
        result = runner.invoke(app, ["report", "summary"])
    assert result.exit_code == 0
    assert "no inventory records" in result.output
    assert "no run records" in result.output


def test_report_summary_connect_error() -> None:
    """ConnectError exits with code 1 and prints a message."""
    import httpx

    mock = _mock_client()
    mock.audit_report.side_effect = httpx.ConnectError("refused")
    with patch("aegis_cli.commands.report.AegisClient", return_value=mock):
        result = runner.invoke(app, ["report", "summary"])
    assert result.exit_code == 1
