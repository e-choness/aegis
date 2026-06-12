"""POST /v1/chat/completions — OpenAI response shape matches schema fixture."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient

_SCHEMA_PATH = Path(__file__).parent / "fixtures" / "openai_completion_schema.json"


def test_chat_completions_shape(client_no_auth: TestClient) -> None:
    resp = client_no_auth.post(
        "/v1/chat/completions",
        json={"model": "default", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    schema = json.loads(_SCHEMA_PATH.read_text())
    data = resp.json()

    # Top-level required keys
    for key in schema["required_keys"]:
        assert key in data, f"Missing key '{key}' in response"

    # object value
    assert data["object"] == schema["object"]

    # id format
    assert data["id"].startswith("chatcmpl-")

    # choices shape
    assert isinstance(data["choices"], list)
    assert len(data["choices"]) >= 1
    choice = data["choices"][0]
    for key in schema["choices_required_keys"]:
        assert key in choice, f"Missing choice key '{key}'"

    # message shape
    for key in schema["message_required_keys"]:
        assert key in choice["message"], f"Missing message key '{key}'"
    assert choice["message"]["role"] == "assistant"

    # finish_reason
    assert choice["finish_reason"] == "stop"

    # usage shape
    for key in schema["usage_required_keys"]:
        assert key in data["usage"], f"Missing usage key '{key}'"


def test_chat_completions_content(client_no_auth: TestClient) -> None:
    resp = client_no_auth.post(
        "/v1/chat/completions",
        json={"model": "default", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "hello from aegis"
