"""ResidencyGuard — fail-closed route filtering by declared region policy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_pack_residency.schema import ResidencyProfile


class ResidencyGuard:
    """A :class:`~aegis_core.guardrails.protocol.Guardrail` that enforces
    data-residency policy by filtering routes against a declared allow-list
    of regions.

    Fail-closed semantics: if no residency profile is found for the route
    (neither an exact match nor a ``"__default__"`` fallback), the request
    is always blocked regardless of *mode* — an undeclared endpoint is a
    config completeness problem, not a policy decision a human can wave
    through.

    A *declared* endpoint outside *allowed_regions* is either blocked
    outright (``mode="block"``, the default) or paused for human review
    (``mode="require_approval"`` — e.g. "route to a non-CA endpoint is
    allowed with sign-off, not forbidden outright").

    Args:
        profiles: Mapping of route name → :class:`ResidencyProfile`. A
            ``"__default__"`` entry applies to any route not otherwise
            listed — this is what ``from_config`` uses for a single
            YAML-declared endpoint shared across routes.
        allowed_regions: Set of region identifiers that are permitted.
            Comparison is case-insensitive.
        mode: ``"block"`` (default) or ``"require_approval"`` for a
            declared-but-disallowed region.
        name: Guard name.
    """

    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(
        self,
        profiles: dict[str, ResidencyProfile],
        allowed_regions: Sequence[str],
        mode: Literal["block", "require_approval"] = "block",
        name: str = "residency",
    ) -> None:
        self.name = name
        self._profiles = profiles
        self._allowed = {r.lower().strip() for r in allowed_regions}
        self._mode = mode

    async def scan(self, state: RunState) -> Verdict:
        """Block (or pause, per *mode*) requests whose region is not in *allowed_regions*."""
        profile = self._profiles.get(state.route) or self._profiles.get("__default__")
        if profile is None:
            return Verdict.block(
                f"residency: no profile declared for route '{state.route}' — fail-closed"
            )

        region = profile.region.lower().strip()
        if region not in self._allowed:
            reason = (
                f"residency: region '{profile.region}' for route '{state.route}' "
                f"is not in the allowed set {sorted(self._allowed)!r}"
            )
            if self._mode == "require_approval":
                return Verdict.require_approval(reason)
            return Verdict.block(reason)

        return Verdict.allow()
