"""Pack factory for aegis.residency — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.config.models import GuardrailConfig
from aegis_core.errors import AegisConfigValidationError
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a GuardNode wrapping a ResidencyGuard in the ingress stage."""
    from aegis_core.guardrails.spine import GuardNode
    from aegis_pack_residency.guard import ResidencyGuard
    from aegis_pack_residency.schema import ResidencyProfile

    region: str | None = getattr(cfg, "region", None)
    if not region:
        raise AegisConfigValidationError(
            f"guardrail {name!r}: aegis.residency requires a 'region' field.",
            guardrail=name,
        )

    allowed_regions: list[str] = getattr(cfg, "allowed_regions", None) or [region]
    # Build a catch-all profile that applies to every route using this guard.
    # Routes without explicit profiles will be routed to the declared region.
    profile = ResidencyProfile(region=region)
    # We use a sentinel key "__default__" so the guard can find it;
    # the guard is wrapped in a node that injects the route at scan time via state.
    # For simplicity we pass profiles as {region: profile} and guard scans state.route.
    profiles: dict[str, ResidencyProfile] = {"__default__": profile}

    guard = ResidencyGuard(profiles=profiles, allowed_regions=allowed_regions, name=name)
    return {"ingress": [GuardNode([guard], name=name)]}
