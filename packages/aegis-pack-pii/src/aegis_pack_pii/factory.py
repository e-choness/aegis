"""Pack factory for aegis.pii — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.config.models import GuardrailConfig
from aegis_core.errors import AegisConfigValidationError
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return the nodes this pack contributes, keyed by stage.

    PII mask declared once → mask node in ingress, unmask node in egress.

    Modes:
        mask (default): mask on ingress, unmask on egress.
        detect: guard node in ingress only (blocks on detection).
    """
    from aegis_pack_pii import PiiMaskNode, PiiUnmaskNode

    mode = cfg.mode or "mask"

    if mode == "mask":
        return {
            "ingress": [PiiMaskNode(name=f"{name}.mask")],  # type: ignore[call-arg]
            "egress": [PiiUnmaskNode(name=f"{name}.unmask")],  # type: ignore[call-arg]
        }

    if mode == "detect":
        from aegis_core.guardrails.spine import GuardNode
        from aegis_pack_pii import PiiMaskGuard

        return {"ingress": [GuardNode([PiiMaskGuard()], name=name)]}

    raise AegisConfigValidationError(
        f"guardrail {name!r}: unknown mode {mode!r} for aegis.pii. "
        "Supported modes: mask, detect.",
        guardrail=name,
    )
