"""Provider contract test kit.

:class:`FakeProvider` is an in-memory stub that satisfies the full
``ModelProvider`` contract without any network calls.

:class:`ProviderContractKit` is a pytest-style helper that asserts every
clause of the contract against a given provider instance.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from aegis_core.providers.models import (
    Chunk,
    CompletionRequest,
    CompletionResult,
    Message,
    ProviderInfo,
    ResidencyInfo,
    ToolCall,
    UsageInfo,
)
from aegis_core.providers.protocol import ModelProvider


class FakeProvider:
    """In-memory ModelProvider for use in tests.

    Attributes:
        name: Provider identifier.
        complete_response: Text returned by :meth:`complete`.
        stream_chunks: List of strings yielded by :meth:`stream`.
        embed_response: Vector returned per text by :meth:`embed`.
    """

    name: str = "fake"

    def __init__(
        self,
        name: str = "fake",
        complete_response: str = "hello from fake",
        stream_chunks: list[str] | None = None,
        embed_response: list[float] | None = None,
        tool_calls_sequence: list[list[ToolCall]] | None = None,
    ) -> None:
        self.name = name
        self.complete_response = complete_response
        self.stream_chunks: list[str] = stream_chunks if stream_chunks is not None else ["hello", " from", " fake"]
        self.embed_response: list[float] = embed_response if embed_response is not None else [0.1, 0.2, 0.3]
        # Each element is the list of ToolCalls returned on call N.
        # When an entry is non-empty, finish_reason is "tool_calls".
        # When exhausted or empty, returns text response.
        self._tool_calls_sequence: list[list[ToolCall]] = tool_calls_sequence or []
        self._call_index: int = 0

        # Capture calls for assertion in tests.
        self.complete_calls: list[CompletionRequest] = []
        self.stream_calls: list[CompletionRequest] = []
        self.embed_calls: list[list[str]] = []

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        self.complete_calls.append(req)
        if self._call_index < len(self._tool_calls_sequence):
            tc = self._tool_calls_sequence[self._call_index]
            self._call_index += 1
            if tc:
                return CompletionResult(
                    text="",
                    model=req.model or "fake-model",
                    usage=UsageInfo(prompt_tokens=5, completion_tokens=5, total_tokens=10),
                    finish_reason="tool_calls",
                    tool_calls=tc,
                )
        else:
            self._call_index += 1
        return CompletionResult(
            text=self.complete_response,
            model=req.model or "fake-model",
            usage=UsageInfo(prompt_tokens=5, completion_tokens=5, total_tokens=10),
            finish_reason="stop",
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[Chunk]:
        self.stream_calls.append(req)

        async def _gen() -> AsyncIterator[Chunk]:
            for i, chunk in enumerate(self.stream_chunks):
                finish = "stop" if i == len(self.stream_chunks) - 1 else None
                yield Chunk(text=chunk, finish_reason=finish)

        return _gen()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [self.embed_response for _ in texts]

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            provider_type="fake",
            models=["fake-model"],
            residency=ResidencyInfo(),
            supports_streaming=True,
            supports_embeddings=True,
        )


class ProviderContractKit:
    """Asserts the full ModelProvider contract against a provider instance.

    Usage in pytest::

        kit = ProviderContractKit(FakeProvider())
        kit.assert_all()

    Or individually::

        kit.assert_isinstance()
        asyncio.run(kit.assert_complete())
        asyncio.run(kit.assert_stream())
        asyncio.run(kit.assert_embed())
        kit.assert_info()
    """

    def __init__(self, provider: object) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Individual assertions
    # ------------------------------------------------------------------

    def assert_isinstance(self) -> None:
        """Provider satisfies the ModelProvider runtime-checkable Protocol."""
        assert isinstance(self._provider, ModelProvider), (
            f"{type(self._provider).__name__} does not satisfy ModelProvider Protocol"
        )

    def assert_name(self) -> None:
        """Provider has a non-empty string ``name`` attribute."""
        name = getattr(self._provider, "name", None)
        assert isinstance(name, str), "Provider.name must be a string"
        assert name, "Provider.name must be non-empty"

    async def assert_complete(self) -> None:
        """complete() returns a CompletionResult with non-empty text."""
        req = CompletionRequest(
            messages=[Message(role="user", content="ping")],
            model="test-model",
        )
        result = await self._provider.complete(req)  # type: ignore[union-attr]
        assert isinstance(result, CompletionResult), "complete() must return CompletionResult"
        assert isinstance(result.text, str), "CompletionResult.text must be str"
        assert isinstance(result.usage, UsageInfo), "CompletionResult.usage must be UsageInfo"

    async def assert_stream(self) -> None:
        """stream() returns an async iterator of Chunks."""
        req = CompletionRequest(
            messages=[Message(role="user", content="ping")],
            model="test-model",
            stream=True,
        )
        gen = await self._provider.stream(req)  # type: ignore[union-attr]
        chunks: list[Chunk] = []
        async for chunk in gen:
            assert isinstance(chunk, Chunk), "stream() must yield Chunk instances"
            chunks.append(chunk)
        assert chunks, "stream() must yield at least one chunk"

    async def assert_embed(self) -> None:
        """embed() returns one vector per input text."""
        texts = ["hello", "world"]
        result = await self._provider.embed(texts)  # type: ignore[union-attr]
        assert isinstance(result, list), "embed() must return list"
        assert len(result) == len(texts), "embed() must return one vector per text"
        for vec in result:
            assert isinstance(vec, list), "each embedding must be a list of floats"
            assert all(isinstance(v, float) for v in vec), "embedding values must be float"

    def assert_info(self) -> None:
        """info() returns a ProviderInfo with required fields."""
        info = self._provider.info()  # type: ignore[union-attr]
        assert isinstance(info, ProviderInfo), "info() must return ProviderInfo"
        assert info.name, "ProviderInfo.name must be non-empty"
        assert info.provider_type, "ProviderInfo.provider_type must be non-empty"
        assert isinstance(info.models, list), "ProviderInfo.models must be a list"
        assert isinstance(info.residency, ResidencyInfo), "ProviderInfo.residency must be ResidencyInfo"

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def assert_all(self) -> None:
        """Run all synchronous contract assertions."""
        self.assert_isinstance()
        self.assert_name()
        self.assert_info()

    async def assert_all_async(self) -> None:
        """Run all contract assertions including async ones."""
        self.assert_all()
        await self.assert_complete()
        await self.assert_stream()
        await self.assert_embed()
