"""CLI commands: `aegis serve` and `aegis dev` (PROJECT_SPEC D17)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer
from rich.console import Console

if TYPE_CHECKING:
    from aegis_core.pipeline.protocol import PipelineNode

_console = Console()
_DEFAULT_KEYS_PATH = Path.home() / ".aegis" / "keys.json"

try:
    from aegis_pack_pii import PiiMaskNode, PiiUnmaskNode
except ImportError:
    PiiMaskNode = None  # type: ignore[misc,assignment]
    PiiUnmaskNode = None  # type: ignore[misc,assignment]

try:
    from aegis_pack_budgets import BudgetGuard, BudgetLedger
except ImportError:
    BudgetGuard = None  # type: ignore[misc,assignment]
    BudgetLedger = None  # type: ignore[misc,assignment]


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
    """Start Aegis in development mode (localhost, no auth, FakeProvider, PII demo).

    Demo mode enables the showcase page with per-IP rate limiting and hard request cap
    (Step 19 safety rails) plus the budget guard for dogfooding.
    """
    import uvicorn

    from aegis_core.guardrails.spine import GuardNode
    from aegis_core.pipeline.executor import PipelineExecutor
    from aegis_core.testing.providers import FakeProvider
    from aegis_server.app import create_app
    from aegis_server.store.run_store import InMemoryRunStore

    executor = PipelineExecutor()
    ingress_nodes: list[PipelineNode] = []
    egress_nodes: list[PipelineNode] = []

    # PII nodes
    if PiiMaskNode is not None:
        ingress_nodes.append(PiiMaskNode())
    if PiiUnmaskNode is not None:
        egress_nodes.append(PiiUnmaskNode())

    # Budget guard for demo dogfooding (Step 19)
    if BudgetGuard is not None and BudgetLedger is not None:
        ingress_nodes.insert(
            0,
            GuardNode([BudgetGuard(BudgetLedger(default_cap=100.0))], name="budget"),
        )

    # Cast to satisfy type checker (runtime types are correct)
    ingress_nodes = cast("list[PipelineNode]", ingress_nodes)  # type: ignore[assignment]
    egress_nodes = cast("list[PipelineNode]", egress_nodes)  # type: ignore[assignment]

    executor.register(
        "default",
        provider=FakeProvider(complete_response="[dev] hello from Aegis"),
        ingress=ingress_nodes or None,
        egress=egress_nodes or None,
    )
    # Step 19: Enable demo_mode for rate limit + hard cap safety rails
    app = create_app(executor, no_auth=True, run_store=InMemoryRunStore(), demo_mode=True)
    msg = f"Starting Aegis dev server on {host}:{port} (auth off"
    if PiiMaskNode is not None:
        msg += ", PII enabled"
    if BudgetGuard is not None and BudgetLedger is not None:
        msg += ", budget guard"
    msg += ", demo safety rails)"
    _console.print(f"[green]{msg}[/green]")
    uvicorn.run(app, host=host, port=port)
