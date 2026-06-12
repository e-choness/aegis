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

    Fail-closed semantics: if the route's declared region is not in
    *allowed_regions*, or if no residency profile is found for the route,
    the request is blocked.

    Args:
        profiles: Mapping of route name → :class:`ResidencyProfile`.
        allowed_regions: Set of region identifiers that are permitted.
            Comparison is case-insensitive.
        name: Guard name.
    """

    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(
        self,
        profiles: dict[str, ResidencyProfile],
        allowed_regions: Sequence[str],
        name: str = "residency",
    ) -> None:
        self.name = name
        self._profiles = profiles
        self._allowed = {r.lower().strip() for r in allowed_regions}

    async def scan(self, state: RunState) -> Verdict:
        """Block requests whose route region is not in *allowed_regions*."""
        profile = self._profiles.get(state.route)
        if profile is None:
            return Verdict.block(
                f"residency: no profile declared for route '{state.route}' — fail-closed"
            )

        region = profile.region.lower().strip()
        if region not in self._allowed:
            return Verdict.block(
                f"residency: region '{profile.region}' for route '{state.route}' "
                f"is not in the allowed set {sorted(self._allowed)!r}"
            )

        return Verdict.allow()
