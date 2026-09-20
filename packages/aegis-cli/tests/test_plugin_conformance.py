"""Tests for `aegis plugin new` / `aegis plugin test` end-to-end behaviour (Phase 3).

Gate: DC uv run pytest packages/aegis-cli -q -k plugin_conformance
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aegis_cli.commands.conformance import check_conformance, run_plugin_tests
from aegis_cli.commands.scaffold import scaffold_plugin
from aegis_core.registry import PluginRegistry


def _uv_pip_install_no_deps(pkg_root: Path) -> None:
    outcome = subprocess.run(
        ["uv", "pip", "install", "--no-deps", "-e", str(pkg_root)],
        capture_output=True,
        text=True,
    )
    assert outcome.returncode == 0, f"install failed:\n{outcome.stdout}\n{outcome.stderr}"


def _uv_pip_uninstall(pkg_name: str) -> None:
    subprocess.run(["uv", "pip", "uninstall", pkg_name], capture_output=True, text=True)


def test_scaffold_installs_and_discovers(tmp_path: Path) -> None:
    """generate -> uv pip install -e -> PluginRegistry().discover() finds it."""
    pkg_root = scaffold_plugin("node", "conformance-discover", output_dir=tmp_path)
    _uv_pip_install_no_deps(pkg_root)
    try:
        registry = PluginRegistry()
        registry.discover()
        node_names = {p.name for p in registry.list_plugins(group="aegis.nodes")}
        pack_names = {p.name for p in registry.list_plugins(group="aegis.packs")}
        assert "conformance_discover" in node_names
        assert "aegis.conformance_discover" in pack_names
    finally:
        _uv_pip_uninstall(pkg_root.name)


def test_scaffold_from_config_roundtrip(tmp_path: Path) -> None:
    """The generated factory.py's from_config() round-trips through the conformance check."""
    pkg_root = scaffold_plugin("node", "conformance-roundtrip", output_dir=tmp_path)
    failures = check_conformance(pkg_root, "node")
    assert failures == [], f"unexpected conformance failures: {failures}"


def test_conformance_fails_on_missing_streaming_attr(tmp_path: Path) -> None:
    """A guardrail stub missing its `streaming` ClassVar fails the protocol check."""
    pkg_root = scaffold_plugin("guardrail", "conformance-broken", output_dir=tmp_path)
    guard_path = pkg_root / "src" / "aegis_guardrail_conformance_broken" / "guard.py"
    content = guard_path.read_text()
    broken = "\n".join(
        line
        for line in content.splitlines()
        if "streaming" not in line and "ClassVar, Literal" not in line
    ).replace("from typing import ClassVar, Literal", "")
    guard_path.write_text(broken)

    failures = check_conformance(pkg_root, "guardrail")
    assert failures, "expected a conformance failure for the missing streaming attribute"
    assert any("Protocol" in f for f in failures)


def test_run_plugin_tests_passes_for_fresh_scaffold(tmp_path: Path) -> None:
    """aegis plugin test's full flow (pytest + conformance) passes on an untouched scaffold."""
    pkg_root = scaffold_plugin("guardrail", "conformance-fresh", output_dir=tmp_path)
    ok, messages = run_plugin_tests(pkg_root)
    assert ok, "\n".join(messages)


@pytest.mark.parametrize("kind", ["guardrail", "node", "provider", "exporter"])
def test_run_plugin_tests_passes_for_every_kind(tmp_path: Path, kind: str) -> None:
    pkg_root = scaffold_plugin(kind, f"conformance-{kind}", output_dir=tmp_path)
    ok, messages = run_plugin_tests(pkg_root)
    assert ok, "\n".join(messages)
