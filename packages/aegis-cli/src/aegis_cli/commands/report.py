"""aegis report — OSFI E-23 compliance summary from the evidence ledger (Phase 3)."""

from __future__ import annotations

import json
import os

import httpx
import typer

from aegis_sdk import AegisClient

app = typer.Typer(help="Compliance report commands.", no_args_is_help=True)

_DEFAULT_URL = "http://localhost:8767"


def _base_url() -> str:
    return os.environ.get("AEGIS_SERVER_URL", _DEFAULT_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("AEGIS_API_KEY", "")


def _make_client() -> AegisClient:
    return AegisClient(base_url=_base_url(), api_key=_api_key())


@app.command("summary")
def summary(
    json_output: bool = typer.Option(False, "--json", help="Output raw report as JSON."),
) -> None:
    """Print OSFI E-23 compliance summary: inventory table, run stats, chain length."""
    try:
        with _make_client() as client:
            report = client.audit_report()
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None

    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return

    generated_at = report.get("generated_at", "")
    chain_length = report.get("chain_length", 0)
    inventory = report.get("inventory", [])
    run_stats = report.get("run_stats", {})

    typer.echo(f"Aegis Compliance Report — {generated_at}")
    typer.echo("═" * 80)

    typer.echo(f"\nModel Inventory  ({len(inventory)} model{'s' if len(inventory) != 1 else ''})")
    typer.echo("─" * 80)
    if inventory:
        typer.echo(f"{'MODEL':30s}  {'RISK':8s}  {'OWNER':20s}  DEPLOYED")
        typer.echo("─" * 80)
        for rec in inventory:
            model_id = str(rec.get("model_id", ""))[:30]
            risk = str(rec.get("model_risk_rating") or "")[:8]
            owner = str(rec.get("model_owner") or "")[:20]
            deployed = str(rec.get("date_of_deployment") or "")[:26]
            typer.echo(f"{model_id:30s}  {risk:8s}  {owner:20s}  {deployed}")
    else:
        typer.echo("  (no inventory records)")

    typer.echo(f"\nRun Statistics  (chain length: {chain_length})")
    typer.echo("─" * 80)
    if run_stats:
        for status, count in sorted(run_stats.items()):
            typer.echo(f"  {status:<20s} {count}")
    else:
        typer.echo("  (no run records)")

    typer.echo("")
