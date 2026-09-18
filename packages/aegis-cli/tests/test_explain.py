"""Tests for `aegis explain` CLI command (Phase 1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from aegis_cli.main import app
from aegis_sdk.models import RunStatusResponse

runner = CliRunner()

_VERDICT_EVENT = {
    "stage": "ingress",
    "node": "pii-guard",
    "event_type": "verdict",
    "data": {"kind": "block", "reason": "pii-detected"},
}

_COMPLETE_EVENT = {
    "stage": "ingress",
    "node": "execute",
    "event_type": "verdict",
    "data": {"kind": "completed"},
}


def _mock_client(run_status: RunStatusResponse, runs: list | None = None) -> MagicMock:
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get_run.return_value = run_status
    client.list_runs.return_value = runs or []
    return client


def test_explain_renders_one_row_per_verdict() -> None:
    status = RunStatusResponse(
        run_id="aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        route="default",
        principal_id="user-1",
        status="completed",
        approvers=[],
        events=[_COMPLETE_EVENT],
        config_digest="sha256:abc123",
    )
    mock = _mock_client(status)
    with patch("aegis_cli.commands.explain.AegisClient", return_value=mock):
        result = runner.invoke(app, ["explain", "aaaabbbb-cccc-dddd-eeee-ffffffffffff"])
    assert result.exit_code == 0
    assert "ingress" in result.output
    assert "execute" in result.output
    assert "COMPLETED" in result.output


def test_explain_block_says_provider_never_called() -> None:
    status = RunStatusResponse(
        run_id="bbbbcccc-dddd-eeee-ffff-000000000000",
        route="default",
        principal_id="user-1",
        status="blocked",
        approvers=[],
        events=[_VERDICT_EVENT],
        config_digest=None,
    )
    mock = _mock_client(status)
    with patch("aegis_cli.commands.explain.AegisClient", return_value=mock):
        result = runner.invoke(app, ["explain", "bbbbcccc-dddd-eeee-ffff-000000000000"])
    assert result.exit_code == 0
    assert "provider never called" in result.output


def test_explain_json_roundtrips_events() -> None:
    import json

    status = RunStatusResponse(
        run_id="ccccdddd-eeee-ffff-0000-111111111111",
        route="default",
        principal_id="user-1",
        status="completed",
        approvers=[],
        events=[_COMPLETE_EVENT],
        config_digest="sha256:deadbeef",
    )
    mock = _mock_client(status)
    with patch("aegis_cli.commands.explain.AegisClient", return_value=mock):
        result = runner.invoke(app, ["explain", "ccccdddd-eeee-ffff-0000-111111111111", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert parsed[0]["event_type"] == "verdict"


def test_explain_last_flag_fetches_most_recent() -> None:
    runs = [
        {"run_id": "run-old", "created_at": "2026-09-01T00:00:00+00:00", "status": "completed"},
        {"run_id": "run-new", "created_at": "2026-09-18T12:00:00+00:00", "status": "completed"},
    ]
    status = RunStatusResponse(
        run_id="run-new",
        route="default",
        principal_id="user-1",
        status="completed",
        approvers=[],
        events=[_COMPLETE_EVENT],
        config_digest=None,
    )
    mock = _mock_client(status, runs=runs)
    with patch("aegis_cli.commands.explain.AegisClient", return_value=mock):
        result = runner.invoke(app, ["explain", "--last"])
    assert result.exit_code == 0
    mock.get_run.assert_called_once_with("run-new")


def test_explain_no_args_exits_1() -> None:
    result = runner.invoke(app, ["explain"])
    assert result.exit_code == 1
