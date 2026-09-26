"""Pack factory for aegis.pii — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.errors import AegisConfigValidationError
from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return the nodes this pack contributes, keyed by stage.

    PII mask declared once → mask node in ingress, unmask node in egress.

    Modes:
        mask (default): mask on ingress, unmask on egress.
        detect: guard node in ingress only (blocks on detection).

    Detection options (both modes):
        entities: entity types to detect, or ``ALL`` (default: identifying
            entities only — see ``aegis_pack_pii.detection.DEFAULT_ENTITIES``).
        threshold: minimum confidence 0-1 (default 0.4).
        allow_list: exact strings never treated as PII.
    """
    from aegis_pack_pii import PiiMaskNode, PiiUnmaskNode
    from aegis_pack_pii.detection import PiiDetector

    try:
        detector = PiiDetector.from_options(
            entities=getattr(cfg, "entities", None),
            threshold=cfg.threshold,
            allow_list=getattr(cfg, "allow_list", None),
        )
    except ValueError as exc:
        raise AegisConfigValidationError(f"guardrail {name!r}: {exc}", guardrail=name) from exc

    mode = cfg.mode or "mask"

    if mode == "mask":
        return {
            "ingress": [PiiMaskNode(name=f"{name}.mask", detector=detector)],
            "egress": [PiiUnmaskNode(name=f"{name}.unmask")],
        }

    if mode == "detect":
        from aegis_core.guardrails.spine import GuardNode
        from aegis_pack_pii import PiiMaskGuard

        return {"ingress": [GuardNode([PiiMaskGuard(detector)], name=name)]}

    raise AegisConfigValidationError(
        f"guardrail {name!r}: unknown mode {mode!r} for aegis.pii. "
        "Supported modes: mask, detect.",
        guardrail=name,
    )
