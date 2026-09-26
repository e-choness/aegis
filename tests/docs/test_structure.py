"""Structural docs checks: diagram count, front-matter files, sidebar integrity."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DOCS_ROOT = ROOT / "docs"

REQUIRED_FRONT_MATTER = [
    ROOT / "docs" / "CONTRIBUTING.md",
    ROOT / "docs" / "CODE_OF_CONDUCT.md",
    ROOT / "docs" / "SECURITY.md",
]

MIN_MERMAID_COUNT = 8


def _extract_mermaid_blocks(text: str) -> list[str]:
    """Return list of mermaid block bodies (without fences)."""
    return re.findall(r"```mermaid\n(.*?)```", text, re.DOTALL)


def test_mermaid_diagram_count() -> None:
    """At least MIN_MERMAID_COUNT mermaid diagrams must exist across docs/."""
    total = 0
    for md_file in DOCS_ROOT.rglob("*.md"):
        blocks = _extract_mermaid_blocks(md_file.read_text(encoding="utf-8"))
        total += len(blocks)
    assert total >= MIN_MERMAID_COUNT, (
        f"Expected >= {MIN_MERMAID_COUNT} mermaid diagrams in docs/, found {total}"
    )


def test_front_matter_files_exist() -> None:
    """CONTRIBUTING.md, CODE_OF_CONDUCT.md, and SECURITY.md must exist."""
    missing = [str(f) for f in REQUIRED_FRONT_MATTER if not f.exists()]
    assert not missing, f"Missing front-matter files: {missing}"


def test_concepts_doc_has_request_lifecycle_diagram() -> None:
    """guide/concepts.md is the single source of truth for the request lifecycle."""
    concepts = DOCS_ROOT / "guide" / "concepts.md"
    assert concepts.exists(), f"{concepts} does not exist"
    blocks = _extract_mermaid_blocks(concepts.read_text(encoding="utf-8"))
    assert blocks, "No mermaid block found in guide/concepts.md"


def test_no_legacy_or_internal_pages() -> None:
    """Docs are for users and plugin authors — no v1 migration or internal decision logs."""
    for rel in ("how-to/migrating-from-v1.md", "explanation/decisions.md"):
        assert not (DOCS_ROOT / rel).exists(), f"docs/{rel} should not be published"


def test_sidebar_links_resolve() -> None:
    """Every internal link in the VitePress sidebar/nav points at an existing page."""
    config = (DOCS_ROOT / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    for link in re.findall(r"link: '(/[^']*)'", config):
        path = link.split("#")[0].rstrip("/")
        candidates = [DOCS_ROOT / f"{path.lstrip('/')}.md", DOCS_ROOT / path.lstrip("/") / "index.md"]
        assert any(c.exists() for c in candidates), f"sidebar link {link!r} has no page"


def test_package_license_copies_match_root() -> None:
    """Every published package ships the root LICENSE verbatim (AGPL-3.0 requires the text)."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from release import PUBLISHED

    root_license = (ROOT / "LICENSE").read_bytes()
    stale = [pkg for pkg in PUBLISHED if (ROOT / pkg / "LICENSE").read_bytes() != root_license]
    assert not stale, f"LICENSE copies differ from the root LICENSE in: {stale} — copy it again"
