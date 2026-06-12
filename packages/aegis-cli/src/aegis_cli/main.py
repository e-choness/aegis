"""Aegis CLI entry point."""

from __future__ import annotations

import typer

from aegis_cli import __version__
from aegis_cli.commands.config import app as config_app

app = typer.Typer(
    name="aegis",
    help="Aegis AI gateway — plugin-first, governed, observable.",
    no_args_is_help=True,
)

app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"aegis {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Aegis AI gateway."""


def run() -> None:
    """Script entry point (project.scripts → aegis)."""
    app()
