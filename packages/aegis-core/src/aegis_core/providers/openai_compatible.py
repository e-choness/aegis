"""OpenAI-compatible provider — thin factory over LiteLLMProvider.

Any endpoint that speaks the OpenAI REST API (Ollama, vLLM, LM Studio, etc.)
can be used via this provider type.  The ``base_url`` and ``api_key`` are
forwarded to litellm which handles the transport.
"""

from __future__ import annotations

from pydantic import SecretStr

from aegis_core.providers.litellm_provider import LiteLLMProvider
from aegis_core.providers.models import ResidencyInfo


class OpenAICompatibleProvider(LiteLLMProvider):
    """ModelProvider for any OpenAI-compatible REST endpoint.

    Configured via ``type: openai_compatible`` in ``aegis.yaml`` or
    ``aegis provider add --type openai_compatible``.
    """

    def __init__(
        self,
        name: str,
        model: str,
        base_url: str,
        api_key: SecretStr | None = None,
        residency: ResidencyInfo | None = None,
    ) -> None:
        super().__init__(
            name=name,
            model=model,
            provider_type="openai_compatible",
            api_key=api_key,
            base_url=base_url,
            residency=residency,
            supported_models=[model],
            supports_embeddings=True,
        )
