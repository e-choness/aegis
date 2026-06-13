"""README.md structural and content checks."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
README = ROOT / "README.md"
SPEC_FILE = ROOT / "PROJECT_SPEC.md"

# Required sections in README, in this order
REQUIRED_SECTIONS = [
    "images/banner-wide.png",           # banner
    "[![CI]",                            # badge row — CI first
    "[![Docs]",
    "[![PyPI version]",
    "[![Python versions]",
    "[![License: MIT]",
    "[![Code style: ruff + pyright]",
    "## What Aegis is",
    "## Architecture",
    "```mermaid",                        # first mermaid = §2
    "## Quick start",
    "## Request lifecycle",
    "## Documentation",
]

# Badge slugs that must appear (and nothing extra from the forbidden list)
REQUIRED_BADGES = [
    "workflows/ci.yml/badge.svg",
    "workflows/docs.yml/badge.svg",
    "img.shields.io/pypi/v/aegis-ai",
    "img.shields.io/pypi/pyversions/aegis-ai",
    "badge/license-MIT",
    "code%20style-ruff",
]

FORBIDDEN_BADGES = ["codecov", "stars", "downloads"]

# Relative links that must exist on disk (resolve from root)
REQUIRED_LINKS = [
    "images/banner-wide.png",
    "docs/CONTRIBUTING.md",
    "docs/SECURITY.md",
]


def _extract_mermaid_blocks(text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)


def _spec_diagram(heading_pattern: str) -> str:
    """Extract a mermaid block from PROJECT_SPEC.md following a heading."""
    spec_text = SPEC_FILE.read_text(encoding="utf-8")
    match = re.search(
        heading_pattern + r".*?```mermaid\n(.*?)```",
        spec_text,
        re.DOTALL,
    )
    assert match, f"Could not find mermaid block after {heading_pattern!r} in PROJECT_SPEC.md"
    return match.group(1)


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
    assert (ROOT / "images" / "banner-wide.png").exists(), (
        "images/banner-wide.png does not exist"
    )


def test_relative_links_resolve() -> None:
    """Referenced relative file paths must resolve to existing files."""
    for rel in REQUIRED_LINKS:
        assert (ROOT / rel).exists(), f"Relative link target does not exist: {rel}"


def test_architecture_diagram_verbatim() -> None:
    """The §2 architecture diagram in README must be byte-identical to PROJECT_SPEC.md §2."""
    spec_diag = _spec_diagram(r"## 2\. Architecture")
    readme_text = README.read_text(encoding="utf-8")
    readme_blocks = _extract_mermaid_blocks(readme_text)
    assert readme_blocks, "No mermaid blocks found in README.md"
    # First mermaid block must be the architecture diagram
    assert readme_blocks[0] == spec_diag, (
        "README architecture diagram (first mermaid block) differs from PROJECT_SPEC.md §2.\n"
        "These must be byte-identical (single source of truth)."
    )


def test_lifecycle_diagram_verbatim() -> None:
    """The §2b lifecycle diagram in README must be byte-identical to PROJECT_SPEC.md §2b."""
    spec_diag = _spec_diagram(r"### 2b\. Request lifecycle")
    readme_text = README.read_text(encoding="utf-8")
    readme_blocks = _extract_mermaid_blocks(readme_text)
    assert len(readme_blocks) >= 2, (
        f"Expected >= 2 mermaid blocks in README.md (architecture + lifecycle), found {len(readme_blocks)}"
    )
    # Second mermaid block must be the lifecycle diagram
    assert readme_blocks[1] == spec_diag, (
        "README lifecycle diagram (second mermaid block) differs from PROJECT_SPEC.md §2b.\n"
        "These must be byte-identical (single source of truth)."
    )
