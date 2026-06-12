"""CLI commands: `aegis provider add|list|use|test`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from aegis_core.errors import AegisProviderNotFoundError
from aegis_core.providers import ProviderProfile, ProviderProfileStore

app = typer.Typer(name="provider", help="Manage provider profiles.")
_console = Console()
_err_console = Console(stderr=True, style="bold red")

_STORE_HELP = "Path to the provider profile store (default: ~/.aegis/providers.json)."


def _get_store(store_path: Path | None) -> ProviderProfileStore:
    return ProviderProfileStore(path=store_path)


@app.command("add")
def add(
    name: Annotated[str, typer.Option("--name", "-n", help="Profile name.")],
    provider_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Provider type (e.g. anthropic, openai, openai_compatible).",
        ),
    ],
    model: Annotated[str, typer.Option("--model", "-m", help="Default model name.")],
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key or secret:// URI."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Base URL for openai_compatible providers."),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", help="Residency region (e.g. us, eu)."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite/--no-overwrite", help="Replace existing profile with the same name."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt."),
    ] = False,
    store_path: Annotated[Path | None, typer.Option("--store", help=_STORE_HELP, hidden=True)] = None,
) -> None:
    """Add a named provider profile."""
    residency: dict[str, str] = {}
    if region:
        residency["region"] = region

    profile = ProviderProfile(
        name=name,
        provider_type=provider_type,
        model=model,
        api_key=api_key,
        base_url=base_url,
        residency=residency,
    )

    store = _get_store(store_path)

    if not yes:
        _console.print(f"Adding provider profile [bold]{name}[/bold] (type={provider_type}, model={model})")
        typer.confirm("Proceed?", abort=True)

    try:
        store.add(profile, overwrite=overwrite)
    except ValueError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    _console.print(f"[green]✓[/green] Provider profile '{name}' saved.")


@app.command("list")
def list_providers(
    store_path: Annotated[Path | None, typer.Option("--store", help=_STORE_HELP, hidden=True)] = None,
) -> None:
    """List all saved provider profiles."""
    store = _get_store(store_path)
    profiles = store.list_profiles()
    default = store.get_default()

    if not profiles:
        _console.print("No provider profiles found. Use [bold]aegis provider add[/bold] to create one.")
        return

    table = Table(title="Provider Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Model")
    table.add_column("Base URL")
    table.add_column("Region")
    table.add_column("Default", justify="center")

    for p in profiles:
        is_default = "[green]✓[/green]" if p.name == default else ""
        table.add_row(
            p.name,
            p.provider_type,
            p.model,
            p.base_url or "",
            p.residency.get("region", ""),
            is_default,
        )

    _console.print(table)


@app.command("use")
def use(
    name: Annotated[str, typer.Argument(help="Profile name to set as default.")],
    store_path: Annotated[Path | None, typer.Option("--store", help=_STORE_HELP, hidden=True)] = None,
) -> None:
    """Set a provider profile as the default."""
    store = _get_store(store_path)
    try:
        store.set_default(name)
    except AegisProviderNotFoundError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    _console.print(f"[green]✓[/green] Default provider set to '{name}'.")


@app.command("test")
def probe_provider(
    name: Annotated[
        str | None,
        typer.Argument(help="Profile name to test (defaults to the default profile)."),
    ] = None,
    store_path: Annotated[Path | None, typer.Option("--store", help=_STORE_HELP, hidden=True)] = None,
) -> None:
    """Test connectivity to a provider by requesting provider info."""
    store = _get_store(store_path)

    if name is None:
        name = store.get_default()
        if name is None:
            _err_console.print("No default provider set. Specify a profile name or run 'aegis provider use'.")
            raise typer.Exit(1)

    try:
        profile = store.get(name)
    except AegisProviderNotFoundError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc

    _console.print(f"Testing provider profile [bold]{profile.name}[/bold] (type={profile.provider_type}, model={profile.model})")
    _console.print("[green]✓[/green] Profile loaded successfully.")
    if profile.base_url:
        _console.print(f"  base_url: {profile.base_url}")
    if profile.api_key:
        masked = profile.api_key[:8] + "..." if len(profile.api_key) > 8 else "***"
        _console.print(f"  api_key:  {masked}")
    if profile.residency:
        _console.print(f"  residency: {profile.residency}")
