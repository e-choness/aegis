"""Pack factory for aegis.llm_guard — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.config.models import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping an LlmGuardAdapter in the ingress stage."""
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_llm_guard import LlmGuardAdapter

    scanners: list[str] = cfg.scanners or ["PromptInjection"]
    threshold: float = cfg.threshold if cfg.threshold is not None else 0.8

    guards = [
        LlmGuardAdapter(scanner_name=scanner, threshold=threshold)
        for scanner in scanners
    ]
    return {"ingress": [GuardNode(guards, name=name)]}
