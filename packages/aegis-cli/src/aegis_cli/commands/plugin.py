"""CLI commands: `aegis plugin list`, `aegis plugin info`, `aegis plugin scaffold`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from aegis_cli.commands.scaffold import _VALID_KINDS, scaffold_plugin
from aegis_core.errors import AegisPluginError, AegisPluginNotFoundError
from aegis_core.registry import PLUGIN_GROUPS, PluginRegistry

app = typer.Typer(name="plugin", help="Discover and inspect Aegis plugins.")
_console = Console()
_err_console = Console(stderr=True, style="bold red")


@app.command("list")
def list_plugins(
    group: Annotated[
        str | None,
        typer.Option("--group", "-g", help="Filter by entry-point group."),
    ] = None,
) -> None:
    """List all discovered Aegis plugins."""
    if group is not None and group not in PLUGIN_GROUPS:
        _err_console.print(
            f"Unknown group '{group}'. Valid groups: {', '.join(PLUGIN_GROUPS)}"
        )
        raise typer.Exit(1)

    try:
        registry = PluginRegistry()
        registry.discover()
    except AegisPluginError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    plugins = registry.list_plugins(group=group)

    if not plugins:
        _console.print("[dim]No plugins found.[/dim]")
        return

    table = Table(title="Aegis Plugins", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Group")
    table.add_column("Package")
    table.add_column("Version")
    table.add_column("Entry Point")

    for p in sorted(plugins, key=lambda x: (x.group, x.name)):
        table.add_row(
            p.name,
            p.group,
            p.dist_name or "[dim]—[/dim]",
            p.dist_version or "[dim]—[/dim]",
            p.value,
        )

    _console.print(table)


@app.command("info")
def info(
    name: Annotated[str, typer.Argument(help="Plugin name.")],
    group: Annotated[
        str | None,
        typer.Option("--group", "-g", help="Entry-point group to search in."),
    ] = None,
) -> None:
    """Show details about a specific plugin."""
    try:
        registry = PluginRegistry()
        registry.discover()
    except AegisPluginError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    if group is not None:
        groups_to_search = [group]
    else:
        groups_to_search = list(PLUGIN_GROUPS)

    found = None
    for g in groups_to_search:
        try:
            found = registry.get(name, g)
            break
        except AegisPluginNotFoundError:
            continue

    if found is None:
        scope = f"group '{group}'" if group else "any group"
        _err_console.print(f"Plugin '{name}' not found in {scope}.")
        raise typer.Exit(1)

    _console.print(f"[bold]Name:[/bold]        {found.name}")
    _console.print(f"[bold]Group:[/bold]       {found.group}")
    _console.print(f"[bold]Package:[/bold]     {found.dist_name or '—'}")
    _console.print(f"[bold]Version:[/bold]     {found.dist_version or '—'}")
    _console.print(f"[bold]Entry Point:[/bold] {found.value}")


@app.command("scaffold")
def scaffold(
    kind: Annotated[
        str,
        typer.Argument(help=f"Plugin kind: {', '.join(_VALID_KINDS)}."),
    ],
    name: Annotated[
        str,
        typer.Argument(help="Plugin name (kebab-case, e.g. my-guard)."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Parent directory for the generated package."),
    ] = Path(".tmp"),
) -> None:
    """Scaffold a publishable Aegis plugin package with a contract-kit test."""
    try:
        pkg_root = scaffold_plugin(kind, name, output_dir=output_dir)
    except ValueError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    _console.print(f"[green]Scaffolded {kind} plugin '{name}'[/green] at {pkg_root}")
    _console.print(f"  Run tests: [cyan]pytest {pkg_root} -v[/cyan]")
