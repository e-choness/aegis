"""Pack factory for aegis.pii — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.errors import AegisConfigValidationError
from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return the nodes this pack contributes, keyed by stage.

    PII mask declared once → mask node in ingress; redact, then unmask, in egress.

    Modes:
        mask (default): mask on ingress; on egress redact PII the model
            produced itself (``<name>.redact``), then restore the user's own
            values (``<name>.unmask``).
        detect: guard node in ingress only (blocks on detection).

    Detection options (both modes):
        entities: entity types to detect, or ``ALL`` (default: identifying
            entities only — see ``aegis_pack_pii.detection.DEFAULT_ENTITIES``).
        threshold: minimum confidence 0-1 (default 0.4).
        allow_list: exact strings never treated as PII.
        spacy_model: spaCy model for names/locations (default
            ``en_core_web_sm``; ``en_core_web_lg`` is larger, rarely better).

    Reply options (mask mode):
        redact_output: redact PII the model produced itself (default true).
        redact_entities: entity types to redact in replies (default: the
            default entities except PERSON — see
            ``aegis_pack_pii.redact_node.DEFAULT_REDACT_ENTITIES``).
    """
    from aegis_pack_pii import PiiMaskNode, PiiUnmaskNode
    from aegis_pack_pii.detection import PiiDetector
    from aegis_pack_pii.redact_node import DEFAULT_REDACT_ENTITIES, PiiRedactNode

    try:
        detector = PiiDetector.from_options(
            entities=getattr(cfg, "entities", None),
            threshold=cfg.threshold,
            allow_list=getattr(cfg, "allow_list", None),
            spacy_model=getattr(cfg, "spacy_model", None),
        )
    except ValueError as exc:
        raise AegisConfigValidationError(f"guardrail {name!r}: {exc}", guardrail=name) from exc

    mode = cfg.mode or "mask"

    if mode == "mask":
        egress: list[PipelineNode] = []
        if getattr(cfg, "redact_output", True) is not False:
            try:
                redactor = PiiDetector.from_options(
                    entities=getattr(cfg, "redact_entities", None) or list(DEFAULT_REDACT_ENTITIES),
                    threshold=cfg.threshold,
                    allow_list=getattr(cfg, "allow_list", None),
                    spacy_model=getattr(cfg, "spacy_model", None),
                )
            except ValueError as exc:
                raise AegisConfigValidationError(
                    f"guardrail {name!r}: redact_entities: {exc}", guardrail=name
                ) from exc
            egress.append(PiiRedactNode(name=f"{name}.redact", detector=redactor))
        egress.append(PiiUnmaskNode(name=f"{name}.unmask"))
        return {
            "ingress": [PiiMaskNode(name=f"{name}.mask", detector=detector)],
            "egress": egress,
        }

    if mode == "detect":
        from aegis_core.guardrails.spine import GuardNode
        from aegis_pack_pii import PiiMaskGuard

        return {"ingress": [GuardNode([PiiMaskGuard(detector)], name=name)]}

    raise AegisConfigValidationError(
        f"guardrail {name!r}: unknown mode {mode!r} for aegis.pii. Supported modes: mask, detect.",
        guardrail=name,
    )
