"""aegis runs — list, inspect, and action paused runs (PROJECT_SPEC D14)."""

from __future__ import annotations

import os

import typer

app = typer.Typer(
    name="runs",
    help="List, inspect, and action pipeline runs.",
    no_args_is_help=True,
)

_DEFAULT_URL = "http://localhost:8767"


def _base_url() -> str:
    return os.environ.get("AEGIS_SERVER_URL", _DEFAULT_URL).rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("AEGIS_API_KEY", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


@app.command("list")
def list_runs(
    pending: bool = typer.Option(False, "--pending", help="Show only paused runs."),
) -> None:
    """List all runs (or only pending ones with --pending)."""
    import httpx

    url = f"{_base_url()}/v1/runs"
    params: dict[str, str] = {}
    if pending:
        params["status"] = "paused"
    try:
        resp = httpx.get(url, headers=_headers(), params=params)
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    if resp.status_code != 200:
        typer.echo(f"Error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(1)
    runs = resp.json()
    if not runs:
        typer.echo("No runs found.")
        return
    for run in runs:
        status = run.get("status", "?")
        typer.echo(f"{run['run_id']}  {status:12s}  {run.get('route', '')}")


@app.command("show")
def show_run(run_id: str = typer.Argument(..., help="Run ID to show.")) -> None:
    """Show details for a specific run."""
    import httpx

    url = f"{_base_url()}/v1/runs/{run_id}"
    try:
        resp = httpx.get(url, headers=_headers())
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    if resp.status_code == 404:
        typer.echo(f"Run '{run_id}' not found.", err=True)
        raise typer.Exit(1)
    if resp.status_code != 200:
        typer.echo(f"Error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(1)
    data = resp.json()
    typer.echo(f"run_id:      {data['run_id']}")
    typer.echo(f"status:      {data['status']}")
    typer.echo(f"route:       {data['route']}")
    typer.echo(f"principal:   {data['principal_id']}")
    approvers = data.get("approvers") or []
    typer.echo(f"approvers:   {', '.join(approvers) if approvers else '(any)'}")


def _resume(run_id: str, decision: str) -> None:
    import httpx

    url = f"{_base_url()}/v1/runs/{run_id}/resume"
    try:
        resp = httpx.post(url, headers=_headers(), json={"decision": decision})
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    if resp.status_code == 403:
        detail = resp.json().get("detail") or {}
        code = detail.get("code", "AEG-AUTH-003") if isinstance(detail, dict) else "AEG-AUTH-003"
        typer.echo(f"{code}: not authorised to {decision} this run.", err=True)
        raise typer.Exit(1)
    if resp.status_code != 200:
        typer.echo(f"Error {resp.status_code}: {resp.text}", err=True)
        raise typer.Exit(1)
    data = resp.json()
    typer.echo(f"Run {run_id} {decision}: status={data['status']}")


@app.command("approve")
def approve_run(run_id: str = typer.Argument(..., help="Run ID to approve.")) -> None:
    """Approve a paused run."""
    _resume(run_id, "approved")


@app.command("deny")
def deny_run(run_id: str = typer.Argument(..., help="Run ID to deny.")) -> None:
    """Deny a paused run."""
    _resume(run_id, "denied")
