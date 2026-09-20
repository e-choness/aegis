"""README.md structural and content checks.

Phase 5 rewrote the README's order deliberately: one-sentence pitch, the
demo scenario, install, the config that produces it, `aegis explain`
output, the four verdicts, then "why this exists" — see
reference/aegis-roadmap.md's Phase 5 section. The two mermaid diagrams that
used to live in the README (architecture, request lifecycle) moved to
docs/explanation/ so the README stays demo-first; see
test_diagrams_moved_to_explanation_docs below instead of a README-vs-spec
byte comparison (PROJECT_SPEC.md does not exist in this repo).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
README = ROOT / "README.md"

# Required sections in README, in this order
REQUIRED_SECTIONS = [
    "images/banner-wide.jpg",           # banner
    "[![CI]",                            # badge row — CI first
    "[![Docs]",
    "[![PyPI version]",
    "[![Python versions]",
    "[![License: MIT]",
    "[![Code style: ruff + pyright]",
    "## See it work",
    "## Install",
    "## The config that produces the scenario above",
    "## `aegis explain` on the denied run",
    "## Four verdicts, nothing else",
    "## Why this exists",
    "## Documentation",
]

# Badge slugs that must appear (and nothing extra from the forbidden list)
REQUIRED_BADGES = [
    "workflows/ci.yml/badge.svg",
    "workflows/docs.yml/badge.svg",
    "img.shields.io/pypi/v/aegis-gateway",
    "img.shields.io/pypi/pyversions/aegis-gateway",
    "badge/license-MIT",
    "code%20style-ruff",
]

FORBIDDEN_BADGES = ["codecov", "stars", "downloads"]

# Relative links that must exist on disk (resolve from root)
REQUIRED_LINKS = [
    "images/banner-wide.jpg",
    "docs/CONTRIBUTING.md",
    "docs/SECURITY.md",
]


def _extract_mermaid_blocks(text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)


def test_readme_exists() -> None:
    assert README.exists(), "README.md does not exist"


def test_required_sections_ordered() -> None:
    """All required sections must appear in README in the declared order."""
    text = README.read_text(encoding="utf-8")
    positions: list[tuple[int, str]] = []
    for marker in REQUIRED_SECTIONS:
        pos = text.find(marker)
        assert pos != -1, f"Required section/marker not found in README: {marker!r}"
        positions.append((pos, marker))

    for i in range(len(positions) - 1):
        a_pos, a_name = positions[i]
        b_pos, b_name = positions[i + 1]
        assert a_pos < b_pos, (
            f"README section ordering wrong: {a_name!r} (pos {a_pos}) "
            f"must come before {b_name!r} (pos {b_pos})"
        )


def test_badge_row_exact() -> None:
    """Required badges present; forbidden badges absent."""
    text = README.read_text(encoding="utf-8")
    for slug in REQUIRED_BADGES:
        assert slug in text, f"Required badge slug missing from README: {slug!r}"
    for slug in FORBIDDEN_BADGES:
        assert slug not in text, f"Forbidden badge found in README: {slug!r}"


def test_banner_path_exists() -> None:
    """The banner image path referenced in README must exist on disk."""
    assert (ROOT / "images" / "banner-wide.jpg").exists(), (
        "images/banner-wide.jpg does not exist"
    )


def test_relative_links_resolve() -> None:
    """Referenced relative file paths must resolve to existing files."""
    for rel in REQUIRED_LINKS:
        assert (ROOT / rel).exists(), f"Relative link target does not exist: {rel}"


def test_readme_names_no_regulation() -> None:
    """Phase 5: name no regulation in the README, not even E-23 — docs only."""
    text = README.read_text(encoding="utf-8")
    for name in ("E-23", "OSFI", "GDPR", "CCPA", "HIPAA", "PIPEDA", "SOC 2", "SOC2"):
        assert name not in text, f"README names a regulation ({name!r}) — keep that in docs/ only"


def test_readme_has_no_mermaid_diagrams() -> None:
    """Phase 5: both diagrams moved to docs/explanation/ so the README stays demo-first."""
    readme_text = README.read_text(encoding="utf-8")
    assert not _extract_mermaid_blocks(readme_text), (
        "README.md should not contain mermaid diagrams — "
        "the architecture and request-lifecycle diagrams live in docs/explanation/ now."
    )


def test_diagrams_moved_to_explanation_docs() -> None:
    """The architecture and request-lifecycle diagrams the README used to carry
    must actually exist in docs/explanation/, not just be deleted.
    """
    architecture = ROOT / "docs" / "explanation" / "architecture.md"
    pipeline = ROOT / "docs" / "explanation" / "pipeline-and-verdicts.md"
    assert _extract_mermaid_blocks(architecture.read_text(encoding="utf-8")), (
        f"Expected a mermaid diagram in {architecture}"
    )
    assert _extract_mermaid_blocks(pipeline.read_text(encoding="utf-8")), (
        f"Expected a mermaid diagram in {pipeline}"
    )
