"""Pack factories for aegis.classification and aegis.policy (aegis.packs entry points)."""

from __future__ import annotations

from aegis_core.errors import AegisConfigValidationError
from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a ClassificationNode in the ingress stage."""
    from aegis_pack_classification.node import ClassificationNode

    return {"ingress": [ClassificationNode(name=name)]}


def policy_from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping a LabelPolicyGuard in the ingress stage.

    ``aegis.yaml`` fields (beyond ``pack``): ``rules``, a list checked in
    order, first match wins; no match allows the request::

        rules:
          - when: {label: classification, in: [secret]}
            verdict: block            # block | require_approval | allow
            reason: credentials must not reach a model
          - when: {label: sensitivity, in: [confidential], min_confidence: 0.8}
            verdict: require_approval

    List it after the node that writes the labels (e.g. ``aegis.classification``).
    """
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_classification.policy import LabelPolicyGuard, PolicyRule

    raw_rules = getattr(cfg, "rules", None)
    if not isinstance(raw_rules, list) or not raw_rules:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.policy requires a non-empty 'rules' list.",
            guardrail=name,
        )
    try:
        rules = [PolicyRule.from_dict(r) for r in raw_rules]
    except (TypeError, ValueError) as exc:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: invalid aegis.policy rule — {exc}", guardrail=name
        ) from exc
    return {"ingress": [GuardNode([LabelPolicyGuard(rules, name=name)], name=name)]}
