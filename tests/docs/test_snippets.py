"""Lint all Python code blocks found in docs/."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

DOCS_ROOT = Path(__file__).parent.parent.parent / "docs"


@pytest.mark.parametrize("example", find_examples(str(DOCS_ROOT)), ids=str)
def test_lint(example: CodeExample, eval_example: EvalExample) -> None:
    eval_example.lint(example)
