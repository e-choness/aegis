"""Tests for aegis-pack-residency.

Gate: DC uv run pytest packages/aegis-pack-residency -q

Key: the residency invariant test — across the full classification x provider
matrix, no route is ever selected whose declared region violates policy, and
unknown region fails closed; lint flags declared-vs-endpoint mismatches.
"""

from __future__ import annotations

import pytest
from aegis_pack_residency import (
    LintViolation,
    ResidencyGuard,
    ResidencyProfile,
    lint_endpoint,
)

from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_core.testing.guardrails import GuardrailContractKit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(route: str, classification: str = "public") -> RunState:
    return RunState(
        run_id="test",
        route=route,
        messages=[Message(role="user", content="hello")],
        labels={"classification": classification},
    )


# ---------------------------------------------------------------------------
# ResidencyProfile schema
# ---------------------------------------------------------------------------


class TestResidencyProfile:
    def test_valid_profile(self) -> None:
        p = ResidencyProfile(region="eu-west-1", jurisdiction="EU")
        assert p.region == "eu-west-1"
        assert p.jurisdiction == "EU"

    def test_empty_region_raises(self) -> None:
        with pytest.raises(ValueError, match="region must not be empty"):
            ResidencyProfile(region="  ", jurisdiction="EU")

    def test_empty_jurisdiction_raises(self) -> None:
        with pytest.raises(ValueError, match="jurisdiction must not be empty"):
            ResidencyProfile(region="eu-west-1", jurisdiction="  ")

    def test_optional_fields(self) -> None:
        p = ResidencyProfile(
            region="us-east-1",
            jurisdiction="US",
            endpoint_url="https://api.example.com",
            source_url="https://docs.example.com",
        )
        assert p.endpoint_url == "https://api.example.com"
        assert p.source_url == "https://docs.example.com"


# ---------------------------------------------------------------------------
# Lint validators — endpoint-region extraction
# ---------------------------------------------------------------------------


class TestLintEndpoint:
    def test_clean_azure_matches(self) -> None:
        profile = ResidencyProfile(
            region="eastus",
            jurisdiction="US",
            endpoint_url="https://myresource.eastus.cognitiveservices.azure.com",
        )
        assert lint_endpoint(profile) == []

    def test_mismatch_azure_flags_violation(self) -> None:
        profile = ResidencyProfile(
            region="eu-west-1",
            jurisdiction="EU",
            endpoint_url="https://myresource.eastus.cognitiveservices.azure.com",
        )
        violations = lint_endpoint(profile)
        assert len(violations) == 1
        assert isinstance(violations[0], LintViolation)
        assert violations[0].detected == "eastus"
        assert violations[0].declared == "eu-west-1"
        assert violations[0].provider == "azure"

    def test_clean_bedrock_matches(self) -> None:
        profile = ResidencyProfile(
            region="eu-central-1",
            jurisdiction="EU",
            endpoint_url="https://bedrock-runtime.eu-central-1.amazonaws.com",
        )
        assert lint_endpoint(profile) == []

    def test_mismatch_bedrock_flags_violation(self) -> None:
        profile = ResidencyProfile(
            region="eu-west-1",
            jurisdiction="EU",
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        )
        violations = lint_endpoint(profile)
        assert len(violations) == 1
        assert violations[0].provider == "bedrock"
        assert violations[0].detected == "us-east-1"

    def test_clean_vertex_matches(self) -> None:
        profile = ResidencyProfile(
            region="europe-west4",
            jurisdiction="EU",
            endpoint_url="https://europe-west4-aiplatform.googleapis.com",
        )
        assert lint_endpoint(profile) == []

    def test_mismatch_vertex_flags_violation(self) -> None:
        profile = ResidencyProfile(
            region="europe-west4",
            jurisdiction="EU",
            endpoint_url="https://us-central1-aiplatform.googleapis.com",
        )
        violations = lint_endpoint(profile)
        assert len(violations) == 1
        assert violations[0].detected == "us-central1"

    def test_clean_openai_region_matches(self) -> None:
        profile = ResidencyProfile(
            region="eu",
            jurisdiction="EU",
            endpoint_url="https://eu.api.openai.com",
        )
        assert lint_endpoint(profile) == []

    def test_mismatch_openai_region_flags_violation(self) -> None:
        profile = ResidencyProfile(
            region="eu",
            jurisdiction="EU",
            endpoint_url="https://us.api.openai.com",
        )
        violations = lint_endpoint(profile)
        assert len(violations) == 1
        assert violations[0].detected == "us"

    def test_unrecognised_url_no_violation(self) -> None:
        profile = ResidencyProfile(
            region="my-region",
            jurisdiction="XY",
            endpoint_url="https://custom.provider.example.com/v1",
        )
        assert lint_endpoint(profile) == []

    def test_empty_url_no_violation(self) -> None:
        profile = ResidencyProfile(region="eu-west-1", jurisdiction="EU")
        assert lint_endpoint(profile) == []

    def test_violation_str(self) -> None:
        v = LintViolation("azure", "eu-west-1", "eastus", "https://example.azure.com")
        s = str(v)
        assert "azure" in s
        assert "eu-west-1" in s
        assert "eastus" in s


# ---------------------------------------------------------------------------
# ResidencyGuard — contract + routing
# ---------------------------------------------------------------------------


class TestResidencyGuardContract:
    def _make_guard(self) -> ResidencyGuard:
        return ResidencyGuard(
            profiles={"eu": ResidencyProfile(region="eu-west-1", jurisdiction="EU")},
            allowed_regions=["eu-west-1"],
        )

    async def test_contract_kit(self) -> None:
        kit = GuardrailContractKit(self._make_guard())
        await kit.assert_all_async()

    def test_name(self) -> None:
        guard = self._make_guard()
        assert guard.name == "residency"

    def test_custom_name(self) -> None:
        guard = ResidencyGuard(profiles={}, allowed_regions=[], name="my_residency")
        assert guard.name == "my_residency"

    def test_streaming_attribute(self) -> None:
        guard = self._make_guard()
        assert guard.streaming == "none"


class TestResidencyGuardRouting:
    def _make_guard(
        self,
        profiles: dict[str, ResidencyProfile],
        allowed_regions: list[str],
    ) -> ResidencyGuard:
        return ResidencyGuard(profiles=profiles, allowed_regions=allowed_regions)

    async def test_allows_route_in_allowed_region(self) -> None:
        guard = self._make_guard(
            profiles={"eu-route": ResidencyProfile(region="eu-west-1", jurisdiction="EU")},
            allowed_regions=["eu-west-1"],
        )
        verdict = await guard.scan(_state("eu-route"))
        assert verdict.is_allow

    async def test_blocks_route_in_disallowed_region(self) -> None:
        guard = self._make_guard(
            profiles={"us-route": ResidencyProfile(region="us-east-1", jurisdiction="US")},
            allowed_regions=["eu-west-1"],
        )
        verdict = await guard.scan(_state("us-route"))
        assert verdict.is_block

    async def test_unknown_route_fail_closed(self) -> None:
        guard = self._make_guard(profiles={}, allowed_regions=["eu-west-1"])
        verdict = await guard.scan(_state("unknown-route"))
        assert verdict.is_block

    async def test_case_insensitive_region_match(self) -> None:
        guard = self._make_guard(
            profiles={"r": ResidencyProfile(region="EU-West-1", jurisdiction="EU")},
            allowed_regions=["eu-west-1"],
        )
        verdict = await guard.scan(_state("r"))
        assert verdict.is_allow

    async def test_block_reason_mentions_route(self) -> None:
        guard = self._make_guard(
            profiles={"my-route": ResidencyProfile(region="us-east-1", jurisdiction="US")},
            allowed_regions=["eu-west-1"],
        )
        verdict = await guard.scan(_state("my-route"))
        assert verdict.is_block
        assert verdict.reason is not None
        assert "my-route" in verdict.reason

    async def test_no_profile_reason_mentions_fail_closed(self) -> None:
        guard = self._make_guard(profiles={}, allowed_regions=["eu"])
        verdict = await guard.scan(_state("orphan"))
        assert verdict.is_block
        assert verdict.reason is not None
        assert "fail-closed" in verdict.reason


# ---------------------------------------------------------------------------
# Residency invariant test: classification x provider matrix
# ---------------------------------------------------------------------------
#
# Across every combination of classification label and provider route,
# no route whose declared region violates the EU-only policy is ever selected.
# Unknown region always fails closed.
#
# This is the canonical test for PROJECT_SPEC D7.


CLASSIFICATIONS = ["public", "pii", "financial", "secret", "medical", "legal"]

# Provider routes with declared residency metadata
_PROFILES: dict[str, ResidencyProfile] = {
    "azure-eu": ResidencyProfile(
        region="westeurope",
        jurisdiction="EU",
        endpoint_url="https://myres.westeurope.cognitiveservices.azure.com",
    ),
    "bedrock-eu": ResidencyProfile(
        region="eu-central-1",
        jurisdiction="EU",
        endpoint_url="https://bedrock-runtime.eu-central-1.amazonaws.com",
    ),
    "vertex-eu": ResidencyProfile(
        region="europe-west4",
        jurisdiction="EU",
        endpoint_url="https://europe-west4-aiplatform.googleapis.com",
    ),
    "azure-us": ResidencyProfile(
        region="eastus",
        jurisdiction="US",
        endpoint_url="https://myres.eastus.cognitiveservices.azure.com",
    ),
    "bedrock-us": ResidencyProfile(
        region="us-east-1",
        jurisdiction="US",
        endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
    ),
    "openai-global": ResidencyProfile(
        region="global",
        jurisdiction="US",
        endpoint_url="",  # no region in URL — lint clean
    ),
}

_EU_REGIONS = {"westeurope", "eu-central-1", "europe-west4"}
_EU_GUARD = ResidencyGuard(
    profiles=_PROFILES,
    allowed_regions=list(_EU_REGIONS),
)
_COMPLIANT_ROUTES = {"azure-eu", "bedrock-eu", "vertex-eu"}
_NON_COMPLIANT_ROUTES = {"azure-us", "bedrock-us", "openai-global"}


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
@pytest.mark.parametrize("route", list(_PROFILES.keys()))
async def test_residency_invariant_eu_only(classification: str, route: str) -> None:
    """EU-only policy: compliant routes allowed, non-compliant routes blocked."""
    verdict = await _EU_GUARD.scan(_state(route, classification))
    if route in _COMPLIANT_ROUTES:
        assert verdict.is_allow, (
            f"Expected allow for route={route!r} classification={classification!r}, "
            f"got {verdict.kind!r}: {verdict.reason}"
        )
    else:
        assert verdict.is_block, (
            f"Expected block for route={route!r} classification={classification!r}, "
            f"got {verdict.kind!r}"
        )


async def test_unknown_route_always_fails_closed() -> None:
    """A route not in profiles must always block regardless of classification."""
    for classification in CLASSIFICATIONS:
        verdict = await _EU_GUARD.scan(_state("unknown-provider", classification))
        assert verdict.is_block, (
            f"Expected fail-closed block for unknown route, "
            f"classification={classification!r}, got {verdict.kind!r}"
        )


# ---------------------------------------------------------------------------
# Lint: declared-vs-endpoint mismatch
# ---------------------------------------------------------------------------


class TestLintDeclaredVsEndpointMatrix:
    """Lint must flag every mismatch in the provider matrix."""

    @pytest.mark.parametrize(("route", "profile"), list(_PROFILES.items()))
    def test_profiles_lint_clean(self, route: str, profile: ResidencyProfile) -> None:
        """All correctly declared profiles in the matrix lint clean."""
        violations = lint_endpoint(profile)
        assert violations == [], (
            f"route={route!r} has unexpected lint violations: {violations}"
        )

    def test_lint_flags_mismatched_bedrock(self) -> None:
        bad_profile = ResidencyProfile(
            region="eu-central-1",
            jurisdiction="EU",
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
        )
        violations = lint_endpoint(bad_profile)
        assert len(violations) == 1
        assert violations[0].provider == "bedrock"

    def test_lint_flags_mismatched_vertex(self) -> None:
        bad_profile = ResidencyProfile(
            region="europe-west4",
            jurisdiction="EU",
            endpoint_url="https://us-central1-aiplatform.googleapis.com",
        )
        violations = lint_endpoint(bad_profile)
        assert len(violations) == 1
        assert violations[0].provider == "vertex"
