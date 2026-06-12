"""CLI commands: `aegis serve` and `aegis dev` (PROJECT_SPEC D17)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

_console = Console()
_DEFAULT_KEYS_PATH = Path.home() / ".aegis" / "keys.json"


def serve(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port.")] = 8000,
    no_auth: Annotated[
        bool,
        typer.Option("--no-auth", help="Disable authentication (insecure)."),
    ] = False,
    keys_path: Annotated[
        Path,
        typer.Option("--keys-file", help="Path to keys JSON file."),
    ] = _DEFAULT_KEYS_PATH,
) -> None:
    """Start the Aegis server (production mode)."""
    import uvicorn

    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_server.app import AEGServError, create_app
    from aegis_server.auth import ApiKeyAuthenticator
    from aegis_server.keys import KeyStore

    executor = PipelineExecutor()
    authenticator: object | None = None
    if not no_auth:
        store = KeyStore(path=keys_path)
        authenticator = ApiKeyAuthenticator(store)

    try:
        app = create_app(executor, authenticator=authenticator, no_auth=no_auth)
    except AEGServError as exc:
        _console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _console.print(f"[green]Starting Aegis server on {host}:{port}[/green]")
    uvicorn.run(app, host=host, port=port)


def dev(
    host: Annotated[str, typer.Option("--host", help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port.")] = 8000,
) -> None:
    """Start Aegis in development mode (localhost, no auth, FakeProvider)."""
    import uvicorn

    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_core.testing.providers import FakeProvider
    from aegis_server.app import create_app

    executor = PipelineExecutor()
    executor.register("default", provider=FakeProvider(complete_response="[dev] hello from Aegis"))
    app = create_app(executor, no_auth=True)
    _console.print(f"[green]Starting Aegis dev server on {host}:{port} (auth off)[/green]")
    uvicorn.run(app, host=host, port=port)
