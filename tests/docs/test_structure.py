"""Structural docs checks: diagram count, front-matter files."""

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


def test_pipeline_doc_has_request_lifecycle_diagram() -> None:
    """pipeline-and-verdicts.md must carry the request-lifecycle diagram.

    This repo has no PROJECT_SPEC.md to compare against (it was never
    committed) — docs/explanation/ is the single source of truth for this
    diagram now, not a byte-identical mirror of an external spec.
    """
    pipeline_file = DOCS_ROOT / "explanation" / "pipeline-and-verdicts.md"
    assert pipeline_file.exists(), f"{pipeline_file} does not exist"
    blocks = _extract_mermaid_blocks(pipeline_file.read_text(encoding="utf-8"))
    assert blocks, "No mermaid block found in pipeline-and-verdicts.md"
