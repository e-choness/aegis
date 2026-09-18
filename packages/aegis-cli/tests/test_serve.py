"""Tests for `aegis serve` CLI command (Phase 0)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aegis_cli.main import app

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "aegis.yaml"
    p.write_text(textwrap.dedent(content))
    return p


_FAKE_YAML = """\
providers:
  fake:
    type: fake
    complete_response: hi
routes:
  default:
    provider: fake
auth:
  type: none
"""


# ── Config-not-found ──────────────────────────────────────────────────────────


def test_serve_missing_config_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["serve", "--config", str(tmp_path / "missing.yaml"), "--no-auth"],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "aegis init" in result.output


# ── Config-validation-error ───────────────────────────────────────────────────


def test_serve_invalid_yaml_exits_1(tmp_path: Path) -> None:
    bad = tmp_path / "aegis.yaml"
    bad.write_text("providers: [this, is, not, a, mapping]\n")
    result = runner.invoke(app, ["serve", "--config", str(bad), "--no-auth"])
    assert result.exit_code == 1


# ── dev command removed ───────────────────────────────────────────────────────


def test_dev_command_no_longer_registered() -> None:
    """The `dev` subcommand was removed in Phase 0."""
    result = runner.invoke(app, ["dev"])
    # Typer exits with 2 for unknown commands
    assert result.exit_code == 2


# ── serve --help includes --config ────────────────────────────────────────────


def test_serve_help_shows_config_option() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output


# ── serve launches (mocked uvicorn) ──────────────────────────────────────────


def test_serve_builds_and_calls_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve() loads config, builds executor, and calls uvicorn.run."""
    p = _write_yaml(tmp_path, _FAKE_YAML)

    launched: list[object] = []

    def fake_run(app: object, **kwargs: object) -> None:
        launched.append(app)

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = runner.invoke(app, ["serve", "--config", str(p), "--no-auth"])
    assert result.exit_code == 0, result.output
    assert len(launched) == 1


def test_serve_prints_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_yaml(tmp_path, _FAKE_YAML)
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: None)

    result = runner.invoke(app, ["serve", "--config", str(p), "--no-auth"])
    assert result.exit_code == 0
    assert "digest=" in result.output
