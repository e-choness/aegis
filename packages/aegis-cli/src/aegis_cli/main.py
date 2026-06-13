"""Aegis CLI entry point."""

from __future__ import annotations

import typer

from aegis_cli import __version__
from aegis_cli.commands.chat import chat
from aegis_cli.commands.config import app as config_app
from aegis_cli.commands.doctor import app as doctor_app
from aegis_cli.commands.init import app as init_app
from aegis_cli.commands.keys import app as keys_app
from aegis_cli.commands.plugin import app as plugin_app
from aegis_cli.commands.policy import app as policy_app
from aegis_cli.commands.provider import app as provider_app
from aegis_cli.commands.rag import app as rag_app
from aegis_cli.commands.runs import app as runs_app
from aegis_cli.commands.serve import dev, serve

app = typer.Typer(
    name="aegis",
    help="Aegis AI gateway — plugin-first, governed, observable.",
    no_args_is_help=True,
)

app.command("chat")(chat)
app.command("serve")(serve)
app.command("dev")(dev)
app.add_typer(config_app, name="config")
app.add_typer(doctor_app, name="doctor")
app.add_typer(init_app, name="init")
app.add_typer(keys_app, name="keys")
app.add_typer(plugin_app, name="plugin")
app.add_typer(policy_app, name="policy")
app.add_typer(provider_app, name="provider")
app.add_typer(rag_app, name="rag")
app.add_typer(runs_app, name="runs")


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
