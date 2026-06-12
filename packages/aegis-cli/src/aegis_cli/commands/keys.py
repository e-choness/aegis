"""CLI commands: `aegis keys create|list|revoke` (PROJECT_SPEC D17)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Manage Aegis virtual API keys.", no_args_is_help=True)
_console = Console()
_DEFAULT_KEYS_PATH = Path.home() / ".aegis" / "keys.json"


def _load_store(keys_path: Path) -> object:
    from aegis_server.keys import KeyStore

    return KeyStore(path=keys_path)


@app.command("create")
def create(
    principal_id: Annotated[str, typer.Argument(help="Principal ID for this key.")],
    team: Annotated[str, typer.Option("--team", "-t", help="Team name.")] = "",
    keys_path: Annotated[
        Path,
        typer.Option("--keys-file", help="Path to keys JSON file."),
    ] = _DEFAULT_KEYS_PATH,
) -> None:
    """Generate a new API key and print it once."""
    from aegis_server.keys import KeyStore

    store = KeyStore(path=keys_path)
    key = store.create(principal_id=principal_id, team=team)
    _console.print("[bold green]Key created.[/bold green] Store this — it will not be shown again.\n")
    _console.print(key, markup=False)


@app.command("list")
def list_keys(
    keys_path: Annotated[
        Path,
        typer.Option("--keys-file", help="Path to keys JSON file."),
    ] = _DEFAULT_KEYS_PATH,
) -> None:
    """List all API keys (no plaintext shown)."""
    from aegis_server.keys import KeyStore

    store = KeyStore(path=keys_path)
    entries = store.list()
    if not entries:
        _console.print("No keys found.")
        return
    table = Table(title="API Keys")
    table.add_column("key_id")
    table.add_column("principal_id")
    table.add_column("team")
    table.add_column("created_at")
    for entry in entries:
        table.add_row(
            str(entry["key_id"]),
            str(entry["principal_id"]),
            str(entry["team"]),
            str(entry["created_at"]),
        )
    _console.print(table)


@app.command("revoke")
def revoke(
    key_id: Annotated[str, typer.Argument(help="The key_id to revoke.")],
    keys_path: Annotated[
        Path,
        typer.Option("--keys-file", help="Path to keys JSON file."),
    ] = _DEFAULT_KEYS_PATH,
) -> None:
    """Revoke an API key by its key_id."""
    from aegis_server.keys import KeyStore

    store = KeyStore(path=keys_path)
    if store.revoke(key_id):
        _console.print(f"[green]Revoked {key_id}.[/green]")
    else:
        _console.print(f"[red]Key '{key_id}' not found.[/red]")
        raise typer.Exit(code=1)
