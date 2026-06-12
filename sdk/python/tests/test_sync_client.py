"""Sync client unit tests — HTTP layer mocked (PROJECT_SPEC D10).

Gate: DC uv run pytest sdk/python -q
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from aegis_sdk import AegisClient
from aegis_sdk.models import ResumeResponse, RunCreateResponse, RunStatusResponse


def _mock_response(status_code: int, body: object) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# create_run
# ---------------------------------------------------------------------------


def test_sync_create_run_posts_to_v1_runs() -> None:
    """create_run() sends POST /v1/runs and returns RunCreateResponse."""
    body = {
        "run_id": "r1",
        "response": "hello",
        "principal_id": "u",
        "events": [],
        "status": "completed",
    }
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "post", return_value=_mock_response(200, body)) as mock_post:
        result = client.create_run([{"role": "user", "content": "hi"}])
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "/v1/runs" in call_kwargs.args[0]
    assert isinstance(result, RunCreateResponse)
    assert result.run_id == "r1"
    assert result.status == "completed"


def test_sync_create_run_background_flag() -> None:
    """create_run(background=True) sends background=true in body."""
    body = {
        "run_id": "r2",
        "response": None,
        "principal_id": "u",
        "events": [],
        "status": "pending",
    }
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "post", return_value=_mock_response(200, body)) as mock_post:
        result = client.create_run([{"role": "user", "content": "hi"}], background=True)
    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["background"] is True
    assert result.status == "pending"


# ---------------------------------------------------------------------------
# get_run
# ---------------------------------------------------------------------------


def test_sync_get_run_gets_v1_runs_id() -> None:
    """get_run() sends GET /v1/runs/{run_id} and returns RunStatusResponse."""
    body = {
        "run_id": "r1",
        "route": "default",
        "principal_id": "u",
        "status": "completed",
        "approvers": [],
    }
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "get", return_value=_mock_response(200, body)) as mock_get:
        result = client.get_run("r1")
    mock_get.assert_called_once_with("/v1/runs/r1")
    assert isinstance(result, RunStatusResponse)
    assert result.run_id == "r1"


# ---------------------------------------------------------------------------
# resume_run
# ---------------------------------------------------------------------------


def test_sync_resume_run_posts_decision() -> None:
    """resume_run() sends POST /v1/runs/{id}/resume with decision in body."""
    body = {"run_id": "r1", "status": "completed", "response": "ok", "events": []}
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "post", return_value=_mock_response(200, body)) as mock_post:
        result = client.resume_run("r1", "approved")
    call_url = mock_post.call_args.args[0]
    assert "/v1/runs/r1/resume" in call_url
    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["decision"] == "approved"
    assert isinstance(result, ResumeResponse)


# ---------------------------------------------------------------------------
# list_runs
# ---------------------------------------------------------------------------


def test_sync_list_runs_calls_audit_endpoint() -> None:
    """list_runs() calls GET /v1/audit and returns the runs list."""
    body = {"runs": [{"run_id": "r1", "status": "completed"}]}
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "get", return_value=_mock_response(200, body)) as mock_get:
        runs = client.list_runs()
    mock_get.assert_called_once()
    assert "/v1/audit" in mock_get.call_args.args[0]
    assert len(runs) == 1


def test_sync_list_runs_passes_filters() -> None:
    """list_runs(principal=..., route=...) passes query params."""
    body = {"runs": []}
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "get", return_value=_mock_response(200, body)) as mock_get:
        client.list_runs(principal="alice", route="default")
    params = mock_get.call_args.kwargs.get("params", {})
    assert params["principal"] == "alice"
    assert params["route"] == "default"


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


def test_sync_chat_posts_to_chat_completions() -> None:
    """chat() sends POST /v1/chat/completions."""
    body = {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "default",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    client = AegisClient("http://test", "key")
    with patch.object(client._client, "post", return_value=_mock_response(200, body)) as mock_post:
        result = client.chat([{"role": "user", "content": "hi"}])
    assert "/v1/chat/completions" in mock_post.call_args.args[0]
    assert result["choices"][0]["message"]["content"] == "hi"


# ---------------------------------------------------------------------------
# stream_chat
# ---------------------------------------------------------------------------


def test_sync_stream_chat_yields_parsed_chunks() -> None:
    """stream_chat() parses SSE lines and yields dicts."""
    chunk1 = json.dumps({"object": "chat.completion.chunk", "choices": [{"delta": {"content": "hello"}}]})
    sse_lines = [f"data: {chunk1}", "data: [DONE]"]

    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = iter(sse_lines)

    client = AegisClient("http://test", "key")
    with patch.object(client._client, "stream", return_value=mock_resp):
        chunks = list(client.stream_chat([{"role": "user", "content": "hi"}]))

    assert len(chunks) == 1
    assert chunks[0]["object"] == "chat.completion.chunk"


# ---------------------------------------------------------------------------
# error propagation
# ---------------------------------------------------------------------------


def test_sync_create_run_raises_on_401() -> None:
    """create_run() raises HTTPStatusError on 401."""
    client = AegisClient("http://test", "badkey")
    with patch.object(client._client, "post", return_value=_mock_response(401, {"detail": "Unauthorized"})):
        with pytest.raises(httpx.HTTPStatusError):
            client.create_run([{"role": "user", "content": "hi"}])
