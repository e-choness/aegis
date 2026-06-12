"""Tests for `aegis config validate` and `aegis config show` CLI commands."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aegis_cli.main import app

runner = CliRunner()


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "aegis.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ── config validate ───────────────────────────────────────────────────────────


def test_validate_valid_config(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path,
        """\
        providers:
          local:
            type: openai_compatible
        routes:
          default:
            provider: local
        """,
    )
    result = runner.invoke(app, ["config", "validate", str(cfg)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "validate", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "AEG-CFG-002" in result.output


def test_validate_bad_route_reference(tmp_path: Path) -> None:
    """Referencing an unknown provider in a route fails validation."""
    cfg = _write_yaml(
        tmp_path,
        """\
        providers: {}
        routes:
          default:
            provider: does_not_exist
        """,
    )
    result = runner.invoke(app, ["config", "validate", str(cfg)])
    assert result.exit_code != 0
    assert "AEG-CFG" in result.output


# ── config show ───────────────────────────────────────────────────────────────


def test_show_redacts_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """config show must not reveal the secret value — only **REDACTED**."""
    monkeypatch.setenv("_CLI_SHOW_SECRET", "super-secret-cli-value")
    cfg = _write_yaml(
        tmp_path,
        """\
        providers:
          p1:
            type: openai_compatible
            api_key: secret://env/_CLI_SHOW_SECRET#value
        routes:
          default:
            provider: p1
        """,
    )
    result = runner.invoke(app, ["config", "show", str(cfg)])
    assert result.exit_code == 0
    assert "super-secret-cli-value" not in result.output
    assert "**REDACTED**" in result.output


def test_show_outputs_valid_json(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path,
        """\
        providers:
          local:
            type: openai_compatible
        routes:
          default:
            provider: local
        """,
    )
    result = runner.invoke(app, ["config", "show", str(cfg)])
    assert result.exit_code == 0
    # Strip rich ANSI escapes before parsing
    import re

    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    clean = ansi_escape.sub("", result.output)
    # Find the JSON block
    start = clean.find("{")
    end = clean.rfind("}") + 1
    assert start >= 0, "No JSON object in output"
    parsed = json.loads(clean[start:end])
    assert "providers" in parsed
    assert "routes" in parsed


def test_show_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0
    assert "AEG-CFG-002" in result.output
