"""LiteLLM-backed ModelProvider — THE ONLY MODULE that imports litellm.

All LLM traffic in Aegis flows through this module. Do not import litellm
anywhere else; use this module's classes instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from pydantic import SecretStr

from aegis_core.errors import (
    AegisProviderAuthError,
    AegisProviderError,
    AegisProviderRateLimitError,
    AegisProviderTimeoutError,
)
from aegis_core.providers.models import (
    Chunk,
    CompletionRequest,
    CompletionResult,
    ProviderInfo,
    ResidencyInfo,
    UsageInfo,
)

if TYPE_CHECKING:
    pass


def _import_litellm() -> object:
    """Lazy import of litellm — deferred so the module itself is importable
    in environments where litellm is not installed."""
    try:
        import litellm  # intentional single import point
        return litellm
    except ImportError as exc:
        raise AegisProviderError(
            "litellm is not installed. Install it with: pip install litellm",
        ) from exc


def _map_litellm_error(exc: Exception) -> AegisProviderError:
    """Map a litellm exception to the appropriate AEG-PRV-* error."""
    cls_name = type(exc).__name__
    msg = str(exc)
    if "AuthenticationError" in cls_name or "auth" in msg.lower() or "api key" in msg.lower():
        return AegisProviderAuthError(msg)
    if "RateLimitError" in cls_name or "rate limit" in msg.lower():
        return AegisProviderRateLimitError(msg)
    if "Timeout" in cls_name or "timeout" in msg.lower():
        return AegisProviderTimeoutError(msg)
    return AegisProviderError(msg)


class LiteLLMProvider:
    """ModelProvider backed by LiteLLM (library mode).

    This class is the ONLY place in the Aegis codebase that calls litellm
    functions.  All provider types (anthropic, openai, openai_compatible, etc.)
    pass through this adapter.
    """

    def __init__(
        self,
        name: str,
        model: str,
        provider_type: str = "openai_compatible",
        api_key: SecretStr | None = None,
        base_url: str | None = None,
        residency: ResidencyInfo | None = None,
        supported_models: list[str] | None = None,
        supports_embeddings: bool = False,
    ) -> None:
        self.name = name
        self._model = model
        self._provider_type = provider_type
        self._api_key = api_key
        self._base_url = base_url
        self._residency = residency or ResidencyInfo()
        self._supported_models = supported_models or [model]
        self._supports_embeddings = supports_embeddings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_kwargs(self) -> dict[str, object]:
        """Build the kwargs dict shared by complete / stream / embed calls."""
        kw: dict[str, object] = {}
        if self._api_key is not None:
            kw["api_key"] = self._api_key.get_secret_value()
        if self._base_url is not None:
            kw["base_url"] = self._base_url
        return kw

    @staticmethod
    def _extract_usage(response: object) -> UsageInfo:
        usage_obj = getattr(response, "usage", None)
        if usage_obj is None:
            return UsageInfo()
        cost = 0.0
        hidden = getattr(response, "_hidden_params", None)
        if hidden and isinstance(hidden, dict):
            cost = float(hidden.get("response_cost") or 0.0)
        return UsageInfo(
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
            cost=cost,
        )

    # ------------------------------------------------------------------
    # ModelProvider interface
    # ------------------------------------------------------------------

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        litellm = _import_litellm()
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        kw = self._call_kwargs()
        if req.max_tokens is not None:
            kw["max_tokens"] = req.max_tokens
        try:
            response = await litellm.acompletion(  # type: ignore[union-attr]
                model=req.model or self._model,
                messages=messages,
                temperature=req.temperature,
                stream=False,
                **kw,
            )
        except Exception as exc:
            raise _map_litellm_error(exc) from exc

        text = response.choices[0].message.content or ""
        finish = response.choices[0].finish_reason or "stop"
        return CompletionResult(
            text=text,
            model=getattr(response, "model", req.model),
            usage=self._extract_usage(response),
            finish_reason=finish,
        )

    async def stream(self, req: CompletionRequest) -> AsyncIterator[Chunk]:
        litellm = _import_litellm()
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        kw = self._call_kwargs()
        if req.max_tokens is not None:
            kw["max_tokens"] = req.max_tokens
        try:
            response = await litellm.acompletion(  # type: ignore[union-attr]
                model=req.model or self._model,
                messages=messages,
                temperature=req.temperature,
                stream=True,
                **kw,
            )
        except Exception as exc:
            raise _map_litellm_error(exc) from exc

        async def _gen() -> AsyncIterator[Chunk]:
            async for chunk in response:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or ""
                finish = chunk.choices[0].finish_reason
                yield Chunk(text=content, finish_reason=finish)

        return _gen()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        litellm = _import_litellm()
        kw = self._call_kwargs()
        try:
            response = await litellm.aembedding(  # type: ignore[union-attr]
                model=self._model,
                input=texts,
                **kw,
            )
        except Exception as exc:
            raise _map_litellm_error(exc) from exc
        return [item["embedding"] for item in response["data"]]

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            provider_type=self._provider_type,
            models=self._supported_models,
            residency=self._residency,
            supports_streaming=True,
            supports_embeddings=self._supports_embeddings,
        )
