"""Structural docs checks: diagram count, front-matter files, §2b verbatim."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DOCS_ROOT = ROOT / "docs"
SPEC_FILE = ROOT / "PROJECT_SPEC.md"

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


def test_section_2b_verbatim() -> None:
    """The §2b request lifecycle diagram in pipeline-and-verdicts.md must match PROJECT_SPEC verbatim."""
    # Extract §2b block from PROJECT_SPEC
    spec_text = SPEC_FILE.read_text(encoding="utf-8")
    # Find the mermaid block that follows "### 2b. Request lifecycle"
    match = re.search(
        r"### 2b\. Request lifecycle.*?```mermaid\n(.*?)```",
        spec_text,
        re.DOTALL,
    )
    assert match, "Could not find §2b mermaid block in PROJECT_SPEC.md"
    spec_diagram = match.group(1)

    # Extract first mermaid block from pipeline-and-verdicts.md
    pipeline_file = DOCS_ROOT / "explanation" / "pipeline-and-verdicts.md"
    assert pipeline_file.exists(), f"{pipeline_file} does not exist"
    pipeline_text = pipeline_file.read_text(encoding="utf-8")
    blocks = _extract_mermaid_blocks(pipeline_text)
    assert blocks, "No mermaid block found in pipeline-and-verdicts.md"
    doc_diagram = blocks[0]

    assert doc_diagram == spec_diagram, (
        "pipeline-and-verdicts.md §2b diagram differs from PROJECT_SPEC.md §2b.\n"
        "These must be byte-identical (single source of truth)."
    )
