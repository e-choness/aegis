"""Tests for `aegis init`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aegis_cli.commands.init import _TEMPLATE, write_init_yaml
from aegis_cli.commands.policy import lint_policy


class TestWriteInitYaml:
    def test_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        assert out.exists()

    def test_file_contains_pii_guardrail(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        content = out.read_text()
        assert "pii" in content
        assert "aegis_pack_pii" in content

    def test_file_is_valid_yaml(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        parsed = yaml.safe_load(out.read_text())
        assert isinstance(parsed, dict)

    def test_does_not_overwrite_by_default(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        out.write_text("original content")
        with pytest.raises(FileExistsError):
            write_init_yaml(out, force=False)
        assert out.read_text() == "original content"

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        out.write_text("old content")
        write_init_yaml(out, force=True)
        assert out.read_text() != "old content"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "dir" / "aegis.yaml"
        write_init_yaml(out)
        assert out.exists()

    def test_pipeline_includes_pii(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        parsed = yaml.safe_load(out.read_text())
        ingress = parsed.get("pipeline", {}).get("ingress", [])
        assert "pii" in ingress

    def test_auth_section_present(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        parsed = yaml.safe_load(out.read_text())
        assert "auth" in parsed


class TestInitLintClean:
    """The generated aegis.yaml must have zero AEG-POL-001 or AEG-POL-002 issues."""

    def test_output_lints_clean_pol001(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        issues = lint_policy(out)
        pol001 = [i for i in issues if i.code == "AEG-POL-001"]
        assert not pol001, (
            "aegis init output has broken pipeline refs:\n"
            + "\n".join(f"  {i.location}: {i.message}" for i in pol001)
        )

    def test_output_lints_clean_pol002(self, tmp_path: Path) -> None:
        """AEG-POL-002 only fires if aegis_pack_pii is not installed.

        This test is skipped when the pack isn't present so CI always passes.
        """
        import importlib.util

        spec = None
        try:
            spec = importlib.util.find_spec("aegis_pack_pii")
        except ModuleNotFoundError:
            pass

        if spec is None:
            pytest.skip("aegis-pack-pii not installed; skipping POL-002 check")

        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        issues = lint_policy(out)
        pol002 = [i for i in issues if i.code == "AEG-POL-002"]
        assert not pol002, (
            "aegis init output has uninstalled pack refs:\n"
            + "\n".join(f"  {i.location}: {i.message}" for i in pol002)
        )

    def test_output_is_valid_yaml(self, tmp_path: Path) -> None:
        out = tmp_path / "aegis.yaml"
        write_init_yaml(out)
        parsed = yaml.safe_load(out.read_text())
        assert isinstance(parsed, dict)

    def test_template_has_commented_sections(self) -> None:
        """Template contains commented-out optional sections."""
        assert "# providers:" in _TEMPLATE
        assert "# routes:" in _TEMPLATE

    def test_template_has_pii_active(self) -> None:
        """PII is active (not commented out)."""
        lines = _TEMPLATE.splitlines()
        pii_lines = [ln for ln in lines if "pii:" in ln and not ln.strip().startswith("#")]
        assert pii_lines, "Expected at least one active 'pii:' line in template"
