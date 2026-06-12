"""Tests for Step 04: providers — protocol, LiteLLM wrapper, profiles, contract kit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegis_core.errors import (
    AegisProviderAuthError,
    AegisProviderError,
    AegisProviderNotFoundError,
    AegisProviderRateLimitError,
    AegisProviderTimeoutError,
)
from aegis_core.providers import (
    Chunk,
    CompletionRequest,
    CompletionResult,
    Message,
    ModelProvider,
    OpenAICompatibleProvider,
    ProviderInfo,
    ProviderProfile,
    ProviderProfileStore,
)
from aegis_core.providers.litellm_provider import LiteLLMProvider, _map_litellm_error
from aegis_core.testing import FakeProvider, ProviderContractKit

# ---------------------------------------------------------------------------
# ModelProvider Protocol
# ---------------------------------------------------------------------------


class TestModelProviderProtocol:
    def test_fake_provider_satisfies_protocol(self) -> None:
        assert isinstance(FakeProvider(), ModelProvider)

    def test_litellm_provider_satisfies_protocol(self) -> None:
        p = LiteLLMProvider(name="test", model="gpt-4o")
        assert isinstance(p, ModelProvider)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), ModelProvider)

    def test_partial_impl_does_not_satisfy_protocol(self) -> None:
        class Partial:
            name = "partial"

            async def complete(self, req: CompletionRequest) -> CompletionResult:  # type: ignore[empty-body]
                ...

        assert not isinstance(Partial(), ModelProvider)


# ---------------------------------------------------------------------------
# FakeProvider + ProviderContractKit
# ---------------------------------------------------------------------------


class TestFakeProvider:
    def test_name(self) -> None:
        p = FakeProvider(name="my-fake")
        assert p.name == "my-fake"

    def test_complete_returns_result(self) -> None:
        p = FakeProvider(complete_response="hi")
        req = CompletionRequest(messages=[Message(role="user", content="hello")], model="m")
        result = asyncio.run(p.complete(req))
        assert isinstance(result, CompletionResult)
        assert result.text == "hi"

    def test_complete_records_call(self) -> None:
        p = FakeProvider()
        req = CompletionRequest(messages=[Message(role="user", content="x")], model="m")
        asyncio.run(p.complete(req))
        assert len(p.complete_calls) == 1
        assert p.complete_calls[0] is req

    def test_stream_yields_chunks(self) -> None:
        p = FakeProvider(stream_chunks=["a", "b", "c"])
        req = CompletionRequest(messages=[Message(role="user", content="x")], model="m", stream=True)

        async def _collect() -> list[Chunk]:
            gen = await p.stream(req)
            return [c async for c in gen]

        chunks = asyncio.run(_collect())
        assert [c.text for c in chunks] == ["a", "b", "c"]
        assert chunks[-1].finish_reason == "stop"

    def test_stream_records_call(self) -> None:
        p = FakeProvider()
        req = CompletionRequest(messages=[Message(role="user", content="x")], model="m")

        async def _run() -> None:
            gen = await p.stream(req)
            async for _ in gen:
                pass

        asyncio.run(_run())
        assert len(p.stream_calls) == 1

    def test_embed_returns_vectors(self) -> None:
        p = FakeProvider(embed_response=[0.1, 0.2])
        result = asyncio.run(p.embed(["a", "b"]))
        assert result == [[0.1, 0.2], [0.1, 0.2]]

    def test_embed_records_call(self) -> None:
        p = FakeProvider()
        asyncio.run(p.embed(["x"]))
        assert p.embed_calls == [["x"]]

    def test_info(self) -> None:
        p = FakeProvider(name="f")
        info = p.info()
        assert isinstance(info, ProviderInfo)
        assert info.name == "f"
        assert info.supports_streaming
        assert info.supports_embeddings


class TestProviderContractKit:
    def test_assert_all_passes_for_fake_provider(self) -> None:
        kit = ProviderContractKit(FakeProvider())
        asyncio.run(kit.assert_all_async())

    def test_assert_isinstance_fails_for_bad_provider(self) -> None:
        kit = ProviderContractKit(object())
        with pytest.raises(AssertionError):
            kit.assert_isinstance()

    def test_assert_name_fails_for_empty_name(self) -> None:
        p = FakeProvider(name="")
        kit = ProviderContractKit(p)
        with pytest.raises(AssertionError):
            kit.assert_name()


# ---------------------------------------------------------------------------
# LiteLLMProvider with litellm stubbed
# ---------------------------------------------------------------------------


def _make_litellm_stub(
    text: str = "mocked",
    model: str = "gpt-4o",
    finish_reason: str = "stop",
    prompt_tokens: int = 5,
    completion_tokens: int = 5,
    cost: float = 0.001,
) -> MagicMock:
    """Build a minimal litellm stub for complete() calls."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    choice = MagicMock()
    choice.message.content = text
    choice.finish_reason = finish_reason

    response = MagicMock()
    response.choices = [choice]
    response.model = model
    response.usage = usage
    response._hidden_params = {"response_cost": cost}

    stub = MagicMock()
    stub.acompletion = AsyncMock(return_value=response)
    return stub


def _make_stream_stub(chunks: list[str]) -> MagicMock:
    """Build a litellm stub for stream() calls."""

    async def _aiter():  # type: ignore[no-untyped-def]
        for i, text in enumerate(chunks):
            delta = MagicMock()
            delta.content = text
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = "stop" if i == len(chunks) - 1 else None
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    response = _aiter()
    stub = MagicMock()
    stub.acompletion = AsyncMock(return_value=response)
    return stub


def _make_embed_stub(vectors: list[list[float]]) -> MagicMock:
    """Build a litellm stub for embed() calls."""
    response = {"data": [{"embedding": v} for v in vectors]}
    stub = MagicMock()
    stub.aembedding = AsyncMock(return_value=response)
    return stub


class TestLiteLLMProvider:
    def _provider(self) -> LiteLLMProvider:
        from pydantic import SecretStr

        return LiteLLMProvider(
            name="test",
            model="gpt-4o",
            api_key=SecretStr("sk-test"),
        )

    def test_complete_returns_result(self) -> None:
        stub = _make_litellm_stub(text="hello world")
        p = self._provider()
        req = CompletionRequest(messages=[Message(role="user", content="hi")], model="gpt-4o")
        with patch("aegis_core.providers.litellm_provider._import_litellm", return_value=stub):
            result = asyncio.run(p.complete(req))
        assert result.text == "hello world"
        assert result.finish_reason == "stop"
        assert result.usage.prompt_tokens == 5
        assert result.usage.cost == pytest.approx(0.001)

    def test_complete_passes_max_tokens(self) -> None:
        stub = _make_litellm_stub()
        p = self._provider()
        req = CompletionRequest(messages=[Message(role="user", content="hi")], model="gpt-4o", max_tokens=100)
        with patch("aegis_core.providers.litellm_provider._import_litellm", return_value=stub):
            asyncio.run(p.complete(req))
        _, kwargs = stub.acompletion.call_args
        assert kwargs.get("max_tokens") == 100

    def test_stream_yields_chunks(self) -> None:
        stub = _make_stream_stub(["tok1", "tok2"])
        p = self._provider()
        req = CompletionRequest(messages=[Message(role="user", content="hi")], model="gpt-4o", stream=True)

        async def _collect() -> list[Chunk]:
            with patch("aegis_core.providers.litellm_provider._import_litellm", return_value=stub):
                gen = await p.stream(req)
                return [c async for c in gen]

        chunks = asyncio.run(_collect())
        assert [c.text for c in chunks] == ["tok1", "tok2"]
        assert chunks[-1].finish_reason == "stop"

    def test_embed_returns_vectors(self) -> None:
        vectors = [[0.1, 0.2], [0.3, 0.4]]
        stub = _make_embed_stub(vectors)
        p = self._provider()
        with patch("aegis_core.providers.litellm_provider._import_litellm", return_value=stub):
            result = asyncio.run(p.embed(["a", "b"]))
        assert result == vectors

    def test_info_fields(self) -> None:
        p = self._provider()
        info = p.info()
        assert info.name == "test"
        assert info.provider_type == "openai_compatible"
        assert "gpt-4o" in info.models

    def test_api_key_not_in_call_kwargs_repr(self) -> None:
        """Secret value must not leak into repr or str."""
        from pydantic import SecretStr

        p = LiteLLMProvider(name="t", model="m", api_key=SecretStr("super-secret"))
        assert "super-secret" not in repr(p._api_key)


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def _exc(self, name: str, msg: str = "") -> Exception:
        exc_class = type(name, (Exception,), {})
        return exc_class(msg)

    def test_auth_error_by_classname(self) -> None:
        exc = _map_litellm_error(self._exc("AuthenticationError"))
        assert isinstance(exc, AegisProviderAuthError)

    def test_auth_error_by_message(self) -> None:
        exc = _map_litellm_error(Exception("Invalid api key"))
        assert isinstance(exc, AegisProviderAuthError)

    def test_rate_limit_by_classname(self) -> None:
        exc = _map_litellm_error(self._exc("RateLimitError"))
        assert isinstance(exc, AegisProviderRateLimitError)

    def test_rate_limit_by_message(self) -> None:
        exc = _map_litellm_error(Exception("rate limit exceeded"))
        assert isinstance(exc, AegisProviderRateLimitError)

    def test_timeout_by_classname(self) -> None:
        exc = _map_litellm_error(self._exc("TimeoutError"))
        assert isinstance(exc, AegisProviderTimeoutError)

    def test_timeout_by_message(self) -> None:
        exc = _map_litellm_error(Exception("request timeout"))
        assert isinstance(exc, AegisProviderTimeoutError)

    def test_generic_error(self) -> None:
        exc = _map_litellm_error(Exception("something else"))
        assert isinstance(exc, AegisProviderError)
        assert type(exc) is AegisProviderError


# ---------------------------------------------------------------------------
# Provider profiles
# ---------------------------------------------------------------------------


class TestProviderProfileStore:
    def test_add_and_get(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        p = ProviderProfile(name="local", provider_type="openai_compatible", model="qwen2.5")
        store.add(p)
        got = store.get("local")
        assert got.name == "local"
        assert got.model == "qwen2.5"

    def test_first_add_sets_default(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="a", provider_type="openai_compatible", model="m"))
        assert store.get_default() == "a"

    def test_add_overwrite_false_raises(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        p = ProviderProfile(name="dup", provider_type="openai_compatible", model="m")
        store.add(p)
        with pytest.raises(ValueError, match="already exists"):
            store.add(p)

    def test_add_overwrite_true_replaces(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="p", provider_type="openai_compatible", model="old"))
        store.add(ProviderProfile(name="p", provider_type="openai_compatible", model="new"), overwrite=True)
        assert store.get("p").model == "new"

    def test_persistence_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "providers.json"
        store1 = ProviderProfileStore(path=path)
        store1.add(ProviderProfile(name="x", provider_type="openai_compatible", model="m1", base_url="http://local"))
        store2 = ProviderProfileStore(path=path)
        got = store2.get("x")
        assert got.base_url == "http://local"

    def test_list_profiles_sorted(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="z", provider_type="openai_compatible", model="m"))
        store.add(ProviderProfile(name="a", provider_type="openai_compatible", model="m"))
        names = [p.name for p in store.list_profiles()]
        assert names == ["a", "z"]

    def test_remove(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="r", provider_type="openai_compatible", model="m"))
        store.remove("r")
        with pytest.raises(AegisProviderNotFoundError):
            store.get("r")

    def test_remove_not_found(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        with pytest.raises(AegisProviderNotFoundError):
            store.remove("ghost")

    def test_remove_default_updates_default(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="a", provider_type="openai_compatible", model="m"))
        store.add(ProviderProfile(name="b", provider_type="openai_compatible", model="m"))
        store.set_default("a")
        store.remove("a")
        # default falls back to next available
        assert store.get_default() != "a"

    def test_set_default(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        store.add(ProviderProfile(name="a", provider_type="openai_compatible", model="m"))
        store.add(ProviderProfile(name="b", provider_type="openai_compatible", model="m"))
        store.set_default("b")
        assert store.get_default() == "b"

    def test_set_default_not_found(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        with pytest.raises(AegisProviderNotFoundError):
            store.set_default("ghost")

    def test_get_not_found(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "providers.json")
        with pytest.raises(AegisProviderNotFoundError) as exc_info:
            store.get("ghost")
        assert "AEG-PRV-005" in str(exc_info.value)

    def test_no_file_loads_empty(self, tmp_path: Path) -> None:
        store = ProviderProfileStore(path=tmp_path / "nonexistent.json")
        assert store.list_profiles() == []
        assert store.get_default() is None

    def test_api_key_persisted_as_uri(self, tmp_path: Path) -> None:
        path = tmp_path / "providers.json"
        store = ProviderProfileStore(path=path)
        store.add(ProviderProfile(name="p", provider_type="anthropic", model="m", api_key="secret://env/ANTHROPIC"))
        raw = json.loads(path.read_text())
        assert raw["profiles"]["p"]["api_key"] == "secret://env/ANTHROPIC"

    def test_residency_persisted(self, tmp_path: Path) -> None:
        path = tmp_path / "providers.json"
        store = ProviderProfileStore(path=path)
        store.add(ProviderProfile(name="p", provider_type="openai_compatible", model="m", residency={"region": "us"}))
        raw = json.loads(path.read_text())
        assert raw["profiles"]["p"]["residency"] == {"region": "us"}


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider
# ---------------------------------------------------------------------------


class TestOpenAICompatibleProvider:
    def test_satisfies_protocol(self) -> None:
        p = OpenAICompatibleProvider(name="local", model="qwen2.5", base_url="http://localhost:11434/v1")
        assert isinstance(p, ModelProvider)

    def test_info_provider_type(self) -> None:
        p = OpenAICompatibleProvider(name="local", model="qwen2.5", base_url="http://localhost:11434/v1")
        assert p.info().provider_type == "openai_compatible"

    def test_complete_passes_base_url(self) -> None:
        stub = _make_litellm_stub()
        p = OpenAICompatibleProvider(name="local", model="qwen2.5", base_url="http://localhost:11434/v1")
        req = CompletionRequest(messages=[Message(role="user", content="hi")], model="qwen2.5")
        with patch("aegis_core.providers.litellm_provider._import_litellm", return_value=stub):
            asyncio.run(p.complete(req))
        _, kwargs = stub.acompletion.call_args
        assert kwargs.get("base_url") == "http://localhost:11434/v1"
