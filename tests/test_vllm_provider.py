"""Tests for VLLMProvider — mocks httpx to avoid a real vLLM server."""
from __future__ import annotations
import pytest
import httpx
import respx
from src.gateway.providers.vllm_provider import VLLMProvider
from src.gateway.providers.base import CompletionRequest

BASE = "http://vllm-test:8001"


def _provider() -> VLLMProvider:
    return VLLMProvider(base_url=BASE)


@respx.mock
@pytest.mark.asyncio
async def test_complete_returns_content():
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "Hello from vLLM"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
    )
    provider = _provider()
    resp = await provider.complete(CompletionRequest(
        model_id="meta-llama/Llama-3-70B-Instruct",
        prompt="Hi",
    ))
    assert resp.content == "Hello from vLLM"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5
    assert resp.cache_hit is False
    assert resp.model_id == "meta-llama/Llama-3-70B-Instruct"


@respx.mock
@pytest.mark.asyncio
async def test_complete_includes_system_prompt():
    captured = {}

    def _capture(request):
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        })

    respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=_capture)
    provider = _provider()
    await provider.complete(CompletionRequest(
        model_id="llama",
        prompt="question",
        system_prompt="You are a reviewer.",
    ))
    messages = captured["body"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a reviewer."
    assert messages[1]["role"] == "user"


@respx.mock
@pytest.mark.asyncio
async def test_complete_raises_on_http_error():
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    provider = _provider()
    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete(CompletionRequest(model_id="llama", prompt="x"))


@respx.mock
@pytest.mark.asyncio
async def test_health_check_true_on_200():
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200))
    assert await _provider().health_check() is True


@respx.mock
@pytest.mark.asyncio
async def test_health_check_false_on_connection_error():
    respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("refused"))
    assert await _provider().health_check() is False


def test_estimate_cost_usd():
    provider = _provider()
    cost = provider.estimate_cost_usd(1_000_000, 0, "local")
    assert abs(cost - 0.10) < 1e-9

    cost_total = provider.estimate_cost_usd(500_000, 500_000, "local")
    assert abs(cost_total - 0.10) < 1e-9
