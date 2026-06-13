"""Validate aegis-config YAML blocks found in docs/."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

DOCS_ROOT = Path(__file__).parent.parent.parent / "docs"

# Top-level keys that indicate an aegis config snippet
_AEGIS_KEYS = {
    "providers",
    "guardrails",
    "routes",
    "telemetry",
    "rag_store",
    "secrets_backend",
    "keys",
    "server",
    "http",
    "policy",
}


def _collect_yaml_examples() -> list[tuple[str, str]]:
    """Return (label, yaml_text) pairs for aegis-config-like YAML blocks in docs/."""
    examples: list[tuple[str, str]] = []
    for md_file in sorted(DOCS_ROOT.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        blocks = re.findall(r"```yaml\n(.*?)```", content, re.DOTALL)
        for i, block in enumerate(blocks):
            try:
                parsed = yaml.safe_load(block)
            except yaml.YAMLError:
                continue
            if not isinstance(parsed, dict):
                continue
            if _AEGIS_KEYS & set(parsed):
                label = f"{md_file.relative_to(DOCS_ROOT)}[{i}]"
                examples.append((label, block))
    return examples


_EXAMPLES = _collect_yaml_examples()


@pytest.mark.parametrize(("label", "yaml_text"), _EXAMPLES, ids=[e[0] for e in _EXAMPLES])
def test_aegis_yaml_block_parses(label: str, yaml_text: str) -> None:
    """Aegis-config-like YAML blocks in docs/ must parse without error."""
    from aegis_core.config import AegisConfig

    parsed = yaml.safe_load(yaml_text)
    assert isinstance(parsed, dict), f"{label}: expected a YAML mapping"
    # Validate through AegisConfig — unknown keys are ignored by default
    AegisConfig.model_validate(parsed)
