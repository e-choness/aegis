"""CLI command: `aegis serve` — load aegis.yaml and start the server."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

_console = Console()
_DEFAULT_KEYS_PATH = Path.home() / ".aegis" / "keys.json"
_DEFAULT_CONFIG = Path("aegis.yaml")


_DEFAULT_LEDGER_DB = Path("aegis_ledger.db")
_DEFAULT_CHECKPOINT_DB = Path("aegis_checkpoints.db")


def serve(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to aegis.yaml."),
    ] = _DEFAULT_CONFIG,
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
    ledger_db: Annotated[
        Path,
        typer.Option("--ledger-db", help="Path to SQLite evidence ledger."),
    ] = _DEFAULT_LEDGER_DB,
    checkpoint_db: Annotated[
        Path,
        typer.Option("--checkpoint-db", help="Path to SQLite HITL checkpoint store."),
    ] = _DEFAULT_CHECKPOINT_DB,
) -> None:
    """Start the Aegis server (loads aegis.yaml, builds pipeline from config)."""
    import asyncio

    import uvicorn

    from aegis_core.config.build import build_executor, config_digest
    from aegis_core.config.loader import load_config
    from aegis_core.errors import AegisConfigNotFoundError, AegisConfigValidationError
    from aegis_core.pipeline.checkpointer import sqlite_checkpointer
    from aegis_server.app import AEGServError, create_app
    from aegis_server.auth import ApiKeyAuthenticator
    from aegis_server.keys import KeyStore
    from aegis_server.store.ledger import SqliteLedgerStore

    # 1. Load and validate config
    try:
        cfg = load_config(config)
    except AegisConfigNotFoundError as exc:
        _console.print(f"[red]{exc}[/red]")
        _console.print(f"  Run [cyan]aegis init --output {config}[/cyan] to create one.")
        raise typer.Exit(code=1) from exc
    except AegisConfigValidationError as exc:
        _console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    digest = config_digest(cfg)

    # 2. Auth
    authenticator: object | None = None
    if not no_auth:
        store = KeyStore(path=keys_path)
        authenticator = ApiKeyAuthenticator(store)

    # 3. Build route_metadata from config
    route_metadata: dict[str, dict] = {}
    for route_name, route_cfg in cfg.routes.items():
        meta: dict = {}
        if route_cfg.owner is not None:
            meta["owner"] = route_cfg.owner
        if route_cfg.risk_rating is not None:
            meta["risk_rating"] = route_cfg.risk_rating
        if route_cfg.review_interval_days is not None:
            meta["review_interval_days"] = route_cfg.review_interval_days
        route_metadata[route_name] = meta

    # 4. Create ledger store
    ledger_store = SqliteLedgerStore(path=str(ledger_db))

    route_count = len(cfg.routes)

    # 5. Build the executor with a real (persistent) checkpointer, then serve.
    #
    # The checkpointer's connection must stay open for the server's entire
    # lifetime — a route that pauses for approval (require_approval) cannot
    # be resumed later without it (AEG-runtime: "Cannot resume a run without
    # a checkpointer"). `uvicorn.run()` opens its own event loop internally,
    # which leaves nowhere to hold that connection open around it — so we
    # drive the async checkpointer context and `uvicorn.Server.serve()`
    # ourselves instead of calling `uvicorn.run()`.
    async def _serve() -> None:
        async with sqlite_checkpointer(str(checkpoint_db)) as checkpointer:
            try:
                executor = build_executor(cfg, checkpointer=checkpointer)
            except (AegisConfigValidationError, Exception) as exc:
                _console.print(f"[red]Failed to build pipeline: {exc}[/red]")
                raise typer.Exit(code=1) from exc

            try:
                app = create_app(
                    executor,
                    authenticator=authenticator,
                    no_auth=no_auth,
                    config_digest=digest,
                    config_path=str(config.resolve()),
                    ledger_store=ledger_store,
                    route_metadata=route_metadata,
                )
            except AEGServError as exc:
                _console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc

            _console.print(
                f"[green]Starting Aegis server on {host}:{port}[/green] "
                f"({route_count} route{'s' if route_count != 1 else ''}, "
                f"digest={digest[:16]}…, ledger={ledger_db}, checkpoints={checkpoint_db})"
            )
            server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
            await server.serve()

    asyncio.run(_serve())
