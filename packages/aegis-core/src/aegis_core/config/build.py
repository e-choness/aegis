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


#: Built-in provider types; any other ``type:`` is looked up as a plugin.
BUILTIN_PROVIDER_TYPES: tuple[str, ...] = ("fake", "anthropic", "openai_compatible")

#: Pipeline stages ``aegis.yaml`` accepts but ``build_executor`` cannot wire yet.
#: Tool governance is configured in Python (``aegis_core.mcp.McpExecuteNode``).
UNWIRED_STAGES: tuple[str, ...] = ("tool_call", "tool_result")


def build_provider(
    pcfg: ProviderConfig,
    *,
    name: str = "",
    registry: PluginRegistry | None = None,
) -> Any:
    """Instantiate a ModelProvider from a ProviderConfig.

    ``fake``, ``anthropic`` and ``openai_compatible`` are built in.  Any other
    ``type`` is resolved from the ``aegis.providers`` entry-point group: the
    registered object's ``from_config(name, cfg)`` is called if it has one,
    otherwise it is constructed with no arguments.
    """
    ptype = pcfg.type

    if ptype == "fake":
        from aegis_core.testing.providers import FakeProvider

        return FakeProvider(
            complete_response=getattr(pcfg, "complete_response", "[fake] hello from Aegis"),
        )

    if ptype == "anthropic":
        from aegis_core.providers.litellm_provider import LiteLLMProvider

        return LiteLLMProvider(
            name=name or ptype,
            model=_required(pcfg, "model", name),
            provider_type="anthropic",
            api_key=pcfg.api_key,
            base_url=pcfg.base_url,
            residency=_residency(pcfg),
        )

    if ptype == "openai_compatible":
        from aegis_core.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            name=name or ptype,
            model=_required(pcfg, "model", name),
            base_url=_required(pcfg, "base_url", name),
            api_key=pcfg.api_key,
            residency=_residency(pcfg),
        )

    return _build_plugin_provider(ptype, pcfg, name=name, registry=registry)


def _required(pcfg: ProviderConfig, field: str, name: str) -> str:
    value = getattr(pcfg, field, None)
    if not value:
        raise AegisConfigValidationError(
            f"Provider {name or pcfg.type!r} (type {pcfg.type!r}) requires {field!r}.",
            provider=name,
            field=field,
        )
    return str(value)


def _residency(pcfg: ProviderConfig) -> Any:
    from aegis_core.providers.models import ResidencyInfo

    if pcfg.residency is None:
        return None
    return ResidencyInfo(
        region=pcfg.residency.region,
        jurisdiction=pcfg.residency.jurisdiction or "",
        source_url=pcfg.residency.source_url or "",
    )


def _build_plugin_provider(
    ptype: str,
    pcfg: ProviderConfig,
    *,
    name: str,
    registry: PluginRegistry | None,
) -> Any:
    from aegis_core.providers.protocol import ModelProvider

    reg = registry if registry is not None else _discovered()
    try:
        target = reg.load(ptype, "aegis.providers")
    except AegisPluginNotFoundError:
        plugins = sorted(p.name for p in reg.list_plugins("aegis.providers"))
        raise AegisConfigValidationError(
            f"Unknown provider type {ptype!r}. Built-in types: "
            f"{', '.join(BUILTIN_PROVIDER_TYPES)}; installed provider plugins: "
            f"{', '.join(plugins) or 'none'}.",
            provider_type=ptype,
        ) from None

    factory = getattr(target, "from_config", None)
    provider = factory(name, pcfg) if callable(factory) else target()
    if not isinstance(provider, ModelProvider):
        raise AegisConfigValidationError(
            f"Provider plugin {ptype!r} did not produce a ModelProvider "
            "(needs name, complete, stream, embed and info).",
            provider_type=ptype,
        )
    return provider


def _check_unwired_stages(cfg: AegisConfig) -> None:
    """Refuse configs whose tool stages would otherwise be silently skipped."""
    pipelines = [("pipeline", cfg.pipeline)] + [
        (f"routes.{rname}.pipeline", route.pipeline)
        for rname, route in cfg.routes.items()
        if route.pipeline is not None
    ]
    for location, pipeline in pipelines:
        for stage in UNWIRED_STAGES:
            if getattr(pipeline, stage):
                raise AegisConfigValidationError(
                    f"{location}.{stage} is set, but aegis serve cannot enforce the "
                    f"{stage} stage yet — refusing to start rather than skip that policy. "
                    "Remove it from aegis.yaml and configure tool governance in Python "
                    "with aegis_core.mcp.McpExecuteNode.",
                    stage=stage,
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
        AegisConfigValidationError: If a pack factory returns an unexpected shape,
            a provider type is unknown, or a stage that can't be wired
            (``tool_call`` / ``tool_result``) is configured.
    """
    _check_unwired_stages(cfg)
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
    providers = {
        pname: build_provider(pcfg, name=pname, registry=reg)
        for pname, pcfg in cfg.providers.items()
    }

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
