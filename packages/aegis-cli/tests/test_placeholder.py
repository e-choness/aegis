"""Placeholder smoke test for aegis-cli."""

from typer.testing import CliRunner

import aegis_cli
from aegis_cli.main import app


def test_aegis_cli_importable() -> None:
    assert aegis_cli.__version__ == "2.0.0a0"


def test_aegis_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "aegis 2.0.0a0" in result.output
