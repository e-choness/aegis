"""Pack factory for aegis.residency — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.errors import AegisConfigValidationError
from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping a ResidencyGuard in the ingress stage.

    ``aegis.yaml`` fields (beyond ``pack``):

    ``region`` (required)
        The declared residency region of the endpoint this guardrail's
        route(s) call, e.g. ``"ca-central-1"``.
    ``jurisdiction`` (required)
        Legal jurisdiction for that region, e.g. ``"CA"``.
    ``allowed_regions`` (optional, default: ``[region]``)
        Regions permitted without escalation.
    ``require_approval`` (optional, default: ``false``)
        When ``true``, a request outside ``allowed_regions`` pauses for
        human review instead of being blocked outright.
    ``apply_when`` (optional, default: ``always``)
        ``sensitive`` enforces only for requests that carry personal or
        sensitive data (PII masked earlier, or a sensitive label).
    ``sensitive_labels`` (optional)
        Label values that count as sensitive; defaults to
        :data:`~aegis_pack_residency.guard.DEFAULT_SENSITIVE_LABELS`.
    """
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_residency.guard import DEFAULT_SENSITIVE_LABELS, ResidencyGuard
    from aegis_pack_residency.schema import ResidencyProfile

    region: str | None = getattr(cfg, "region", None)
    if not region:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.residency requires a 'region' field.",
            guardrail=name,
        )

    jurisdiction: str | None = getattr(cfg, "jurisdiction", None)
    if not jurisdiction:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.residency requires a 'jurisdiction' field.",
            guardrail=name,
        )

    allowed_regions: list[str] = getattr(cfg, "allowed_regions", None) or [region]
    require_approval: bool = bool(getattr(cfg, "require_approval", False))

    # A "__default__" profile applies to every route this guard is attached
    # to — a single YAML declaration describes one endpoint's residency, not
    # a per-route map (see ResidencyGuard's per-route `profiles` dict, which
    # is the lower-level API used when one guard instance polices several
    # routes with different declared regions).
    profile = ResidencyProfile(region=region, jurisdiction=jurisdiction)
    profiles: dict[str, ResidencyProfile] = {"__default__": profile}

    apply_when = getattr(cfg, "apply_when", None) or "always"
    if apply_when not in ("always", "sensitive"):
        raise AegisConfigValidationError(
            f"guardrail {name!r}: apply_when must be 'always' or 'sensitive', got {apply_when!r}.",
            guardrail=name,
        )
    sensitive_labels = getattr(cfg, "sensitive_labels", None) or DEFAULT_SENSITIVE_LABELS

    mode = "require_approval" if require_approval else "block"
    guard = ResidencyGuard(
        profiles=profiles,
        allowed_regions=allowed_regions,
        mode=mode,
        name=name,
        apply_when=apply_when,
        sensitive_labels=[str(label) for label in sensitive_labels],
    )
    return {"ingress": [GuardNode([guard], name=name)]}
