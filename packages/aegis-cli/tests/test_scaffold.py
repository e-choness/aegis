"""Tests for `aegis plugin scaffold`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aegis_cli.commands.scaffold import scaffold_plugin


class TestScaffoldGuardrail:
    def test_creates_package_root(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        assert result.exists()
        assert result.name == "aegis-guardrail-demo-guard"

    def test_creates_pyproject_toml(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        toml = result / "pyproject.toml"
        assert toml.exists()
        content = toml.read_text()
        assert 'name = "aegis-guardrail-demo-guard"' in content
        assert '"aegis.guardrails"' in content

    def test_creates_src_package(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        src_pkg = result / "src" / "aegis_guardrail_demo_guard"
        assert (src_pkg / "__init__.py").exists()
        assert (src_pkg / "guard.py").exists()

    def test_creates_contract_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        test_file = result / "tests" / "test_contract.py"
        assert test_file.exists()
        content = test_file.read_text()
        assert "GuardrailContractKit" in content
        assert "DemoGuard" in content

    def test_creates_conftest(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        conftest = result / "conftest.py"
        assert conftest.exists()
        assert "sys.path" in conftest.read_text()

    def test_guard_impl_has_scan_method(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        impl = (result / "src" / "aegis_guardrail_demo_guard" / "guard.py").read_text()
        assert "async def scan" in impl
        assert "Verdict.allow()" in impl

    def test_guard_impl_has_streaming_classvar(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        impl = (result / "src" / "aegis_guardrail_demo_guard" / "guard.py").read_text()
        assert "streaming" in impl
        assert "ClassVar" in impl

    def test_entry_point_in_pyproject(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        toml = (result / "pyproject.toml").read_text()
        assert "aegis_guardrail_demo_guard" in toml

    def test_scaffolded_guardrail_passes_contract_test(self, tmp_path: Path) -> None:
        """The generated tests/ pass with zero edits to the scaffold."""
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        outcome = subprocess.run(
            [sys.executable, "-m", "pytest", str(result / "tests"), "-q", "--tb=short"],
            capture_output=True,
            text=True,
        )
        assert outcome.returncode == 0, (
            f"Scaffolded guardrail tests failed:\n{outcome.stdout}\n{outcome.stderr}"
        )


class TestScaffoldProvider:
    def test_creates_package_root(self, tmp_path: Path) -> None:
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        assert result.exists()
        assert result.name == "aegis-provider-my-llm"

    def test_creates_pyproject_toml(self, tmp_path: Path) -> None:
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        toml = (result / "pyproject.toml").read_text()
        assert 'name = "aegis-provider-my-llm"' in toml
        assert '"aegis.providers"' in toml

    def test_creates_src_package(self, tmp_path: Path) -> None:
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        src_pkg = result / "src" / "aegis_provider_my_llm"
        assert (src_pkg / "__init__.py").exists()
        assert (src_pkg / "provider.py").exists()

    def test_creates_contract_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        test_file = result / "tests" / "test_contract.py"
        assert test_file.exists()
        content = test_file.read_text()
        assert "ProviderContractKit" in content
        assert "MyLlm" in content

    def test_provider_impl_has_complete_method(self, tmp_path: Path) -> None:
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        impl = (result / "src" / "aegis_provider_my_llm" / "provider.py").read_text()
        assert "async def complete" in impl
        assert "async def stream" in impl
        assert "async def embed" in impl
        assert "def info" in impl

    def test_scaffolded_provider_passes_contract_test(self, tmp_path: Path) -> None:
        """The generated tests/ pass with zero edits to the scaffold."""
        result = scaffold_plugin("provider", "my-llm", output_dir=tmp_path)
        outcome = subprocess.run(
            [sys.executable, "-m", "pytest", str(result / "tests"), "-q", "--tb=short"],
            capture_output=True,
            text=True,
        )
        assert outcome.returncode == 0, (
            f"Scaffolded provider tests failed:\n{outcome.stdout}\n{outcome.stderr}"
        )


class TestScaffoldInvalidKind:
    def test_invalid_kind_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown plugin kind"):
            scaffold_plugin("node", "my-node", output_dir=tmp_path)

    def test_invalid_kind_message_lists_valid(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="guardrail"):
            scaffold_plugin("invalid", "x", output_dir=tmp_path)


class TestScaffoldNaming:
    def test_kebab_name_converted_to_snake(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "my-awesome-guard", output_dir=tmp_path)
        assert (result / "src" / "aegis_guardrail_my_awesome_guard").exists()

    def test_class_name_is_pascal_case(self, tmp_path: Path) -> None:
        result = scaffold_plugin("guardrail", "my-awesome-guard", output_dir=tmp_path)
        impl = (result / "src" / "aegis_guardrail_my_awesome_guard" / "guard.py").read_text()
        assert "class MyAwesomeGuard" in impl
