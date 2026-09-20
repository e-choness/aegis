"""CLI-level tests for `aegis plugin new` and `aegis plugin test`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aegis_cli.main import app

runner = CliRunner()


def test_plugin_new_creates_package(tmp_path: Path) -> None:
    result = runner.invoke(app, ["plugin", "new", "cli-demo", "--kind", "node", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "aegis-node-cli-demo").exists()
    assert "aegis plugin test" in result.output


def test_plugin_new_rejects_unknown_kind(tmp_path: Path) -> None:
    result = runner.invoke(app, ["plugin", "new", "x", "--kind", "database", "--output-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "Unknown plugin kind" in result.output


def test_plugin_test_passes_for_fresh_scaffold(tmp_path: Path) -> None:
    new_result = runner.invoke(
        app, ["plugin", "new", "cli-test-demo", "--kind", "provider", "--output-dir", str(tmp_path)]
    )
    assert new_result.exit_code == 0, new_result.output
    pkg_root = tmp_path / "aegis-provider-cli-test-demo"

    test_result = runner.invoke(app, ["plugin", "test", str(pkg_root)])
    assert test_result.exit_code == 0, test_result.output
    assert "All checks passed" in test_result.output


def test_plugin_test_missing_path() -> None:
    result = runner.invoke(app, ["plugin", "test", "/no/such/path"])
    assert result.exit_code == 1
