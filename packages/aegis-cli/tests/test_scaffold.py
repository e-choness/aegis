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

    def test_creates_factory_with_packs_entry_point(self, tmp_path: Path) -> None:
        """Guardrails are declarable in YAML `guardrails:` via the aegis.packs group (Phase 0)."""
        result = scaffold_plugin("guardrail", "demo-guard", output_dir=tmp_path)
        assert (result / "src" / "aegis_guardrail_demo_guard" / "factory.py").exists()
        toml = (result / "pyproject.toml").read_text()
        assert '"aegis.packs"' in toml
        assert "factory:from_config" in toml

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


class TestScaffoldNode:
    def test_creates_package_root(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        assert result.exists()
        assert result.name == "aegis-node-demo-node"

    def test_creates_pyproject_toml(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        toml = (result / "pyproject.toml").read_text()
        assert 'name = "aegis-node-demo-node"' in toml
        assert '"aegis.nodes"' in toml

    def test_creates_src_package(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        src_pkg = result / "src" / "aegis_node_demo_node"
        assert (src_pkg / "__init__.py").exists()
        assert (src_pkg / "node.py").exists()

    def test_creates_contract_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        content = (result / "tests" / "test_contract.py").read_text()
        assert "NodeContractKit" in content
        assert "DemoNode" in content

    def test_node_impl_has_run_method(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        impl = (result / "src" / "aegis_node_demo_node" / "node.py").read_text()
        assert "async def run" in impl
        assert "RunStateDelta" in impl

    def test_creates_factory_with_packs_entry_point(self, tmp_path: Path) -> None:
        """Nodes are declarable in YAML `guardrails:` via the aegis.packs group (Phase 0)."""
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        assert (result / "src" / "aegis_node_demo_node" / "factory.py").exists()
        toml = (result / "pyproject.toml").read_text()
        assert '"aegis.packs"' in toml
        assert "factory:from_config" in toml

    def test_creates_factory_roundtrip_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        content = (result / "tests" / "test_factory.py").read_text()
        assert "from_config" in content
        assert "test_from_config_is_deterministic" in content

    def test_scaffolded_node_passes_contract_test(self, tmp_path: Path) -> None:
        """The generated tests/ pass with zero edits to the scaffold."""
        result = scaffold_plugin("node", "demo-node", output_dir=tmp_path)
        outcome = subprocess.run(
            [sys.executable, "-m", "pytest", str(result / "tests"), "-q", "--tb=short"],
            capture_output=True,
            text=True,
        )
        assert outcome.returncode == 0, (
            f"Scaffolded node tests failed:\n{outcome.stdout}\n{outcome.stderr}"
        )


class TestScaffoldExporter:
    def test_creates_package_root(self, tmp_path: Path) -> None:
        result = scaffold_plugin("exporter", "demo-sink", output_dir=tmp_path)
        assert result.exists()
        assert result.name == "aegis-exporter-demo-sink"

    def test_creates_pyproject_toml(self, tmp_path: Path) -> None:
        result = scaffold_plugin("exporter", "demo-sink", output_dir=tmp_path)
        toml = (result / "pyproject.toml").read_text()
        assert 'name = "aegis-exporter-demo-sink"' in toml
        assert '"aegis.exporters"' in toml
        # Exporters aren't declared via YAML `guardrails:` — no packs entry.
        assert '"aegis.packs"' not in toml

    def test_creates_contract_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("exporter", "demo-sink", output_dir=tmp_path)
        content = (result / "tests" / "test_contract.py").read_text()
        assert "ExporterContractKit" in content
        assert "DemoSink" in content

    def test_exporter_impl_has_export_method(self, tmp_path: Path) -> None:
        result = scaffold_plugin("exporter", "demo-sink", output_dir=tmp_path)
        impl = (result / "src" / "aegis_exporter_demo_sink" / "exporter.py").read_text()
        assert "async def export" in impl

    def test_scaffolded_exporter_passes_contract_test(self, tmp_path: Path) -> None:
        result = scaffold_plugin("exporter", "demo-sink", output_dir=tmp_path)
        outcome = subprocess.run(
            [sys.executable, "-m", "pytest", str(result / "tests"), "-q", "--tb=short"],
            capture_output=True,
            text=True,
        )
        assert outcome.returncode == 0, (
            f"Scaffolded exporter tests failed:\n{outcome.stdout}\n{outcome.stderr}"
        )


class TestScaffoldInvalidKind:
    def test_invalid_kind_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown plugin kind"):
            scaffold_plugin("database", "my-thing", output_dir=tmp_path)

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
