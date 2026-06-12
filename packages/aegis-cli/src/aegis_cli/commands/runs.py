"""aegis runs — list, inspect, and action pipeline runs (PROJECT_SPEC D14, D10)."""

from __future__ import annotations

import os

import httpx
import typer

from aegis_sdk import AegisClient

app = typer.Typer(
    name="runs",
    help="List, inspect, and action pipeline runs.",
    no_args_is_help=True,
)

_DEFAULT_URL = "http://localhost:8767"


def _base_url() -> str:
    return os.environ.get("AEGIS_SERVER_URL", _DEFAULT_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("AEGIS_API_KEY", "")


def _make_client() -> AegisClient:
    return AegisClient(base_url=_base_url(), api_key=_api_key())


@app.command("list")
def list_runs(
    pending: bool = typer.Option(False, "--pending", help="Show only paused/pending runs."),
) -> None:
    """List all runs (or only pending/paused ones with --pending)."""
    try:
        with _make_client() as client:
            runs = client.list_runs()
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None
    if pending:
        runs = [r for r in runs if r.get("status") in ("paused", "pending")]
    if not runs:
        typer.echo("No runs found.")
        return
    for run in runs:
        status = run.get("status", "?")
        typer.echo(f"{run['run_id']}  {status:12s}  {run.get('route', '')}")


@app.command("show")
def show_run(run_id: str = typer.Argument(..., help="Run ID to show.")) -> None:
    """Show details for a specific run."""
    try:
        with _make_client() as client:
            data = client.get_run(run_id)
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            typer.echo(f"Run '{run_id}' not found.", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"run_id:      {data.run_id}")
    typer.echo(f"status:      {data.status}")
    typer.echo(f"route:       {data.route}")
    typer.echo(f"principal:   {data.principal_id}")
    typer.echo(f"approvers:   {', '.join(data.approvers) if data.approvers else '(any)'}")


def _resume(run_id: str, decision: str) -> None:
    try:
        with _make_client() as client:
            data = client.resume_run(run_id, decision)
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            detail = exc.response.json().get("detail") or {}
            code = detail.get("code", "AEG-AUTH-003") if isinstance(detail, dict) else "AEG-AUTH-003"
            typer.echo(f"{code}: not authorised to {decision} this run.", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Run {run_id} {decision}: status={data.status}")


@app.command("approve")
def approve_run(run_id: str = typer.Argument(..., help="Run ID to approve.")) -> None:
    """Approve a paused run."""
    _resume(run_id, "approved")


@app.command("deny")
def deny_run(run_id: str = typer.Argument(..., help="Run ID to deny.")) -> None:
    """Deny a paused run."""
    _resume(run_id, "denied")
