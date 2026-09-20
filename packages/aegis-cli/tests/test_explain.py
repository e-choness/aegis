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
    # Real shape: GuardNode/assembler.py key the verdict kind as "verdict",
    # never "kind" — this fixture used to say "kind" and every test still
    # passed because explain.py had the identical bug (fell through to "?").
    "data": {"verdict": "block", "guard": "pii-guard", "reason": "pii-detected"},
}

_COMPLETE_EVENT = {
    "stage": "ingress",
    "node": "execute",
    "event_type": "verdict",
    "data": {"verdict": "completed"},
}

_REQUIRE_APPROVAL_EVENT = {
    "stage": "ingress",
    "node": "residency_ca",
    "event_type": "verdict",
    "data": {
        "verdict": "require_approval",
        "guard": "residency_ca",
        "reason": "residency: region 'us-east-1' is not in the allowed set ['ca-central-1']",
    },
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


def test_explain_renders_real_verdict_key_not_fallback() -> None:
    """Regression: explain.py used to key off "kind"/"status", which no real
    verdict-emitting node ever sets — every row rendered as an uncoloured "?".
    """
    status = RunStatusResponse(
        run_id="ddddeeee-ffff-0000-1111-222222222222",
        route="underwriting",
        principal_id="anonymous",
        status="paused",
        approvers=[],
        events=[_REQUIRE_APPROVAL_EVENT],
        config_digest="sha256:abc",
    )
    mock = _mock_client(status)
    with patch("aegis_cli.commands.explain.AegisClient", return_value=mock):
        result = runner.invoke(app, ["explain", "ddddeeee-ffff-0000-1111-222222222222"])
    assert result.exit_code == 0
    assert "REQUIRE_APPROVAL" in result.output
    assert "?" not in result.output.split("\n")[2]  # the rendered verdict row
    assert "not in the allowed set" in result.output
