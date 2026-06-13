"""Tests proving aegis runs commands route through AegisClient SDK (PROJECT_SPEC D10).

Gate: DC uv run pytest packages/aegis-cli -q
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from aegis_cli.commands.runs import app
from aegis_sdk.models import ResumeResponse, RunStatusResponse

runner = CliRunner()


def _make_mock_client(
    *,
    list_runs_result: list[Any] | None = None,
    get_run_result: RunStatusResponse | None = None,
    resume_result: ResumeResponse | None = None,
) -> MagicMock:
    """Return a mock AegisClient context manager."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    if list_runs_result is not None:
        client.list_runs.return_value = list_runs_result
    if get_run_result is not None:
        client.get_run.return_value = get_run_result
    if resume_result is not None:
        client.resume_run.return_value = resume_result
    return client


# ---------------------------------------------------------------------------
# aegis runs list
# ---------------------------------------------------------------------------


def test_runs_list_calls_sdk_list_runs() -> None:
    """aegis runs list routes through AegisClient.list_runs()."""
    mock = _make_mock_client(list_runs_result=[])
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["list"])
    mock.list_runs.assert_called_once()
    assert result.exit_code == 0


def test_runs_list_prints_run_rows() -> None:
    """aegis runs list prints run_id, status, and route columns."""
    runs = [{"run_id": "abc123", "status": "completed", "route": "default"}]
    mock = _make_mock_client(list_runs_result=runs)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["list"])
    assert "abc123" in result.output
    assert "completed" in result.output


def test_runs_list_empty_prints_no_runs_found() -> None:
    """aegis runs list with no runs prints 'No runs found.'"""
    mock = _make_mock_client(list_runs_result=[])
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["list"])
    assert "No runs found." in result.output


def test_runs_list_pending_filters_by_status() -> None:
    """aegis runs list --pending shows only paused/pending runs."""
    runs = [
        {"run_id": "r1", "status": "completed", "route": "default"},
        {"run_id": "r2", "status": "paused", "route": "default"},
    ]
    mock = _make_mock_client(list_runs_result=runs)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["list", "--pending"])
    assert "r2" in result.output
    assert "r1" not in result.output


def test_runs_list_connect_error_exits_1() -> None:
    """aegis runs list on ConnectError exits with code 1."""
    mock = _make_mock_client()
    mock.list_runs.side_effect = httpx.ConnectError("refused")
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["list"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# aegis runs show
# ---------------------------------------------------------------------------


def test_runs_show_calls_sdk_get_run() -> None:
    """aegis runs show <id> routes through AegisClient.get_run()."""
    run = RunStatusResponse(
        run_id="r1", route="default", principal_id="alice", status="completed", approvers=[]
    )
    mock = _make_mock_client(get_run_result=run)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["show", "r1"])
    mock.get_run.assert_called_once_with("r1")
    assert result.exit_code == 0


def test_runs_show_prints_run_fields() -> None:
    """aegis runs show prints run_id, status, route, principal, approvers."""
    run = RunStatusResponse(
        run_id="abc123",
        route="default",
        principal_id="alice",
        status="paused",
        approvers=["bob"],
    )
    mock = _make_mock_client(get_run_result=run)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["show", "abc123"])
    assert "abc123" in result.output
    assert "paused" in result.output
    assert "alice" in result.output
    assert "bob" in result.output


def test_runs_show_not_found_exits_1() -> None:
    """aegis runs show <missing> on 404 exits with code 1."""
    mock_resp = MagicMock(status_code=404, text="Not found")
    mock = _make_mock_client()
    mock.get_run.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=mock_resp
    )
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["show", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# aegis runs approve / deny
# ---------------------------------------------------------------------------


def test_runs_approve_calls_sdk_resume_approved() -> None:
    """aegis runs approve routes through AegisClient.resume_run('approved')."""
    resp = ResumeResponse(run_id="r1", status="completed", response=None, events=[])
    mock = _make_mock_client(resume_result=resp)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["approve", "r1"])
    mock.resume_run.assert_called_once_with("r1", "approved")
    assert result.exit_code == 0
    assert "approved" in result.output


def test_runs_deny_calls_sdk_resume_denied() -> None:
    """aegis runs deny routes through AegisClient.resume_run('denied')."""
    resp = ResumeResponse(run_id="r1", status="denied", response=None, events=[])
    mock = _make_mock_client(resume_result=resp)
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["deny", "r1"])
    mock.resume_run.assert_called_once_with("r1", "denied")
    assert result.exit_code == 0


def test_runs_approve_403_prints_auth_error() -> None:
    """aegis runs approve on 403 prints AEG-AUTH-003 error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_resp.json.return_value = {"detail": {"code": "AEG-AUTH-003"}}
    mock = _make_mock_client()
    mock.resume_run.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=mock_resp
    )
    with patch("aegis_cli.commands.runs.AegisClient", return_value=mock):
        result = runner.invoke(app, ["approve", "r1"])
    assert result.exit_code == 1
    assert "AEG-AUTH-003" in result.output
