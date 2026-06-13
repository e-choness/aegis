"""Endpoint-region lint validators for Azure / Bedrock / Vertex / OpenAI-region URLs."""

from __future__ import annotations

import re

from aegis_pack_residency.schema import ResidencyProfile

# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------

# Each entry: (provider_name, url_pattern, region_extractor)
# region_extractor: callable(match) -> str | None
_ENDPOINT_PATTERNS: list[tuple[str, re.Pattern[str], object]] = [
    # Azure OpenAI: https://<resource>.openai.azure.com or
    # https://<resource>.<region>.cognitiveservices.azure.com
    (
        "azure",
        re.compile(
            r"https://[\w-]+\.((?P<region>[a-z0-9-]+)\.)?cognitiveservices\.azure\.com",
            re.IGNORECASE,
        ),
        lambda m: m.group("region"),
    ),
    # AWS Bedrock: https://bedrock-runtime.<region>.amazonaws.com
    (
        "bedrock",
        re.compile(
            r"https://bedrock(?:-runtime)?\.(?P<region>[a-z0-9-]+)\.amazonaws\.com",
            re.IGNORECASE,
        ),
        lambda m: m.group("region"),
    ),
    # Google Vertex: https://<region>-aiplatform.googleapis.com
    (
        "vertex",
        re.compile(
            r"https://(?P<region>[a-z0-9-]+)-aiplatform\.googleapis\.com",
            re.IGNORECASE,
        ),
        lambda m: m.group("region"),
    ),
    # OpenAI regional: https://api.openai.com/<region>/... (hypothetical) or
    # Azure-hosted OpenAI deployments at regional sub-domains
    (
        "openai-region",
        re.compile(
            r"https://(?P<region>[a-z0-9-]+)\.api\.openai\.com",
            re.IGNORECASE,
        ),
        lambda m: m.group("region"),
    ),
]


class LintViolation:
    """Describes a single lint rule violation."""

    def __init__(self, provider: str, declared: str, detected: str, url: str) -> None:
        self.provider = provider
        self.declared = declared
        self.detected = detected
        self.url = url

    def __str__(self) -> str:
        return (
            f"[{self.provider}] endpoint region '{self.detected}' "
            f"does not match declared region '{self.declared}' (url={self.url})"
        )

    def __repr__(self) -> str:
        return f"LintViolation({self})"


def lint_endpoint(profile: ResidencyProfile) -> list[LintViolation]:
    """Validate that *profile.endpoint_url* encodes the declared *profile.region*.

    Returns a list of :class:`LintViolation` objects — empty means lint clean.
    An unrecognised URL pattern produces no violation (not every provider
    embeds the region in the URL).
    """
    url = profile.endpoint_url
    if not url:
        return []

    violations: list[LintViolation] = []
    for provider, pattern, extractor in _ENDPOINT_PATTERNS:
        m = pattern.search(url)
        if m is None:
            continue
        detected = extractor(m)  # type: ignore[operator]
        if detected is None:
            continue
        # Normalise: lower-case, strip whitespace
        if detected.lower().strip() != profile.region.lower().strip():
            violations.append(
                LintViolation(
                    provider=provider,
                    declared=profile.region,
                    detected=detected,
                    url=url,
                )
            )
    return violations
