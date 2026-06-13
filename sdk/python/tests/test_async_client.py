"""Async client integration tests against the ASGI app (PROJECT_SPEC D10).

Gate: DC uv run pytest sdk/python -q
"""

from __future__ import annotations

import httpx
import pytest

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_sdk import AsyncAegisClient
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.run_store import InMemoryRunStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport() -> tuple[httpx.ASGITransport, str]:
    """Build an ASGI transport and return (transport, api_key)."""
    fake = FakeProvider(complete_response="sdk response")
    ex = PipelineExecutor()
    ex.register("default", provider=fake)
    ks = KeyStore()
    api_key = ks.create(principal_id="sdk-user", team="t")
    store = InMemoryRunStore()
    app = create_app(ex, authenticator=ApiKeyAuthenticator(ks), run_store=store)
    return httpx.ASGITransport(app=app), api_key  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_create_run_returns_response() -> None:
    """AsyncAegisClient.create_run() returns a RunCreateResponse with status."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        result = await client.create_run([{"role": "user", "content": "hello"}])
    assert result.run_id
    assert result.status == "completed"
    assert result.response == "sdk response"


@pytest.mark.asyncio
async def test_async_create_run_background_returns_pending() -> None:
    """AsyncAegisClient.create_run(background=True) returns status=pending."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        result = await client.create_run(
            [{"role": "user", "content": "hi"}], background=True
        )
    assert result.status == "pending"
    assert result.response is None


@pytest.mark.asyncio
async def test_async_get_run_returns_status() -> None:
    """AsyncAegisClient.get_run() polls run status."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        created = await client.create_run([{"role": "user", "content": "hi"}])
        polled = await client.get_run(created.run_id)
    assert polled.run_id == created.run_id
    assert polled.status == "completed"
    assert polled.route == "default"


@pytest.mark.asyncio
async def test_async_list_runs_returns_entries() -> None:
    """AsyncAegisClient.list_runs() returns audit records."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        await client.create_run([{"role": "user", "content": "audit test"}])
        runs = await client.list_runs()
    assert len(runs) == 1
    assert runs[0]["principal_id"] == "sdk-user"


@pytest.mark.asyncio
async def test_async_list_runs_filter_by_route() -> None:
    """AsyncAegisClient.list_runs(route=...) filters results."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        await client.create_run([{"role": "user", "content": "x"}], route="default")
        runs = await client.list_runs(route="default")
        no_runs = await client.list_runs(route="nonexistent")
    assert len(runs) == 1
    assert no_runs == []


@pytest.mark.asyncio
async def test_async_chat_returns_completion() -> None:
    """AsyncAegisClient.chat() calls /v1/chat/completions and returns JSON."""
    transport, api_key = _make_transport()
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        result = await client.chat([{"role": "user", "content": "hi"}], model="default")
    assert "choices" in result
    assert result["choices"][0]["message"]["content"] == "sdk response"


@pytest.mark.asyncio
async def test_async_stream_chat_yields_chunks() -> None:
    """AsyncAegisClient.stream_chat() yields parsed SSE chunks."""
    transport, api_key = _make_transport()
    chunks: list[dict[str, object]] = []
    async with AsyncAegisClient("http://test", api_key, transport=transport) as client:
        async for chunk in client.stream_chat(
            [{"role": "user", "content": "stream"}], model="default"
        ):
            chunks.append(chunk)
    assert len(chunks) >= 1
    assert any(c.get("object") == "chat.completion.chunk" for c in chunks)


@pytest.mark.asyncio
async def test_async_unauthenticated_raises() -> None:
    """AsyncAegisClient without a key gets a 401 HTTPStatusError."""
    transport, _key = _make_transport()
    async with AsyncAegisClient("http://test", "", transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.create_run([{"role": "user", "content": "hi"}])
    assert exc_info.value.response.status_code == 401
