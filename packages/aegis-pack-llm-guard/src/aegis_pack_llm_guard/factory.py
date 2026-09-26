"""Pack factory for aegis.llm_guard — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping an LlmGuardAdapter in the ingress stage."""
    import importlib.util

    from aegis_core.errors import AegisConfigValidationError
    from aegis_core.guardrails.protocol import Guardrail
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_llm_guard import LlmGuardAdapter

    # Fail at startup, not on the first request, when the optional library is absent.
    if importlib.util.find_spec("llm_guard") is None:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.llm_guard needs the LLM Guard library — "
            'pip install "aegis-gateway-pack-llm-guard[llm-guard]"',
            guardrail=name,
        )

    scanners: list[str] = cfg.scanners or ["PromptInjection"]
    threshold: float = cfg.threshold if cfg.threshold is not None else 0.8

    guards: list[Guardrail] = [
        LlmGuardAdapter(scanner_name=scanner, threshold=threshold)
        for scanner in scanners
    ]
    return {"ingress": [GuardNode(guards, name=name)]}
