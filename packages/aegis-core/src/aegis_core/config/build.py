"""Build a PipelineExecutor from an AegisConfig.

Entry point for the serve command — call ``build_executor(cfg)`` to get
a fully wired executor ready to handle requests.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from aegis_core.config.models import AegisConfig, ProviderConfig
from aegis_core.errors import AegisConfigValidationError, AegisPluginNotFoundError
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.pipeline.protocol import PipelineNode

if TYPE_CHECKING:
    from aegis_core.registry.discovery import PluginRegistry


def _discovered() -> PluginRegistry:
    from aegis_core.registry.discovery import PluginRegistry

    reg = PluginRegistry()
    reg.discover()
    return reg


def build_provider(pcfg: ProviderConfig) -> Any:
    """Instantiate a ModelProvider from a ProviderConfig."""
    ptype = pcfg.type

    if ptype == "fake":
        from aegis_core.testing.providers import FakeProvider

        return FakeProvider(
            complete_response=getattr(pcfg, "complete_response", "[fake] hello from Aegis"),
        )

    if ptype == "anthropic":
        from aegis_core.providers.litellm_provider import LiteLLMProvider

        return LiteLLMProvider(
            api_key=pcfg.api_key.get_secret_value() if pcfg.api_key else None,
            model=pcfg.model,
            base_url=pcfg.base_url,
        )

    if ptype == "openai_compatible":
        from aegis_core.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=pcfg.api_key.get_secret_value() if pcfg.api_key else None,
            base_url=pcfg.base_url or "",
            model=pcfg.model or "",
        )

    raise AegisConfigValidationError(
        f"Unknown provider type {ptype!r}. "
        "Supported types: fake, anthropic, openai_compatible.",
        provider_type=ptype,
    )


def _collect(
    names: list[str],
    contributions: dict[str, dict[str, list[PipelineNode]]],
    stage: str,
) -> list[PipelineNode]:
    """Collect nodes for *stage* from named guardrails in declaration order."""
    result: list[PipelineNode] = []
    for name in names:
        nodes = contributions.get(name, {}).get(stage, [])
        result.extend(nodes)
    return result


def build_executor(
    cfg: AegisConfig,
    *,
    registry: PluginRegistry | None = None,
    checkpointer: Any | None = None,
) -> PipelineExecutor:
    """Build and return a :class:`PipelineExecutor` from *cfg*.

    Args:
        cfg: Validated AegisConfig.
        registry: Optional pre-discovered PluginRegistry.  A fresh one is
            discovered when ``None``.
        checkpointer: Optional LangGraph-style checkpointer passed through to
            PipelineExecutor.

    Raises:
        AegisPluginNotFoundError: If a guardrail's pack is not installed.
        AegisConfigValidationError: If a pack factory returns an unexpected shape.
    """
    reg = registry if registry is not None else _discovered()

    # 1. Instantiate every declared guardrail once via its pack factory.
    contributions: dict[str, dict[str, list[PipelineNode]]] = {}
    for gname, gcfg in cfg.guardrails.items():
        factory = reg.load(gcfg.pack, "aegis.packs")  # raises AegisPluginNotFoundError
        result = factory(gname, gcfg)
        if not isinstance(result, dict):
            raise AegisConfigValidationError(
                f"Pack factory for {gcfg.pack!r} must return a dict[str, list[PipelineNode]], "
                f"got {type(result).__name__}",
                guardrail=gname,
            )
        contributions[gname] = result

    # 2. Build providers.
    providers = {pname: build_provider(pcfg) for pname, pcfg in cfg.providers.items()}

    # 3. Compile one pipeline per route.
    ex = PipelineExecutor(checkpointer=checkpointer)
    for rname, route in cfg.routes.items():
        stages = route.pipeline if route.pipeline is not None else cfg.pipeline
        ex.register(
            rname,
            provider=providers[route.provider],
            ingress=_collect(stages.ingress, contributions, "ingress") or None,
            egress=_collect(stages.egress, contributions, "egress") or None,
        )
    return ex


def config_digest(cfg: AegisConfig) -> str:
    """Return a stable SHA-256 digest of the config (secrets redacted).

    This is the "model version" field for E-23 Appendix 1 inventory records.
    Keys are sorted for stability; secrets are replaced with ``**REDACTED**``.
    """
    canonical = json.dumps(cfg.safe_dict(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
