"""aegis explain — show verdict trail for a pipeline run (Phase 1)."""

from __future__ import annotations

import json
import os

import httpx
import typer

from aegis_sdk import AegisClient

_DEFAULT_URL = "http://localhost:8767"

_COLOUR = {
    "block": "red",
    "blocked": "red",
    "denied": "red",
    "paused": "yellow",
    "require_approval": "yellow",
    "completed": "green",
    "allow": "green",
    "sanitize": "cyan",
    "pass": "green",
}


def _base_url() -> str:
    return os.environ.get("AEGIS_SERVER_URL", _DEFAULT_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("AEGIS_API_KEY", "")


def _make_client() -> AegisClient:
    return AegisClient(base_url=_base_url(), api_key=_api_key())


def _event_data(event: dict[str, object]) -> dict[str, object]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _colour_kind(kind: str) -> str:
    colour = _COLOUR.get(kind.lower(), "white")
    return typer.style(kind.upper(), fg=colour, bold=True)


def explain(
    run_id: str | None = typer.Argument(None, help="Run ID to explain."),
    last: bool = typer.Option(False, "--last", help="Use the most recent run."),
    json_output: bool = typer.Option(False, "--json", help="Output raw events as JSON."),
) -> None:
    """Show the verdict trail for a pipeline run."""
    if run_id is None and not last:
        typer.echo("Provide a run_id or use --last.", err=True)
        raise typer.Exit(1)

    try:
        with _make_client() as client:
            if last:
                runs = client.list_runs()
                if not runs:
                    typer.echo("No runs found.", err=True)
                    raise typer.Exit(1)
                run_id = max(runs, key=lambda r: r.get("created_at", ""))["run_id"]
            data = client.get_run(run_id)  # type: ignore[arg-type]
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            typer.echo(f"Run '{run_id}' not found.", err=True)
            raise typer.Exit(1) from None
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None

    if json_output:
        typer.echo(json.dumps(data.events, indent=2))
        return

    # Header
    short_id = data.run_id[:8] if len(data.run_id) > 8 else data.run_id
    digest_display = data.config_digest or "(none)"
    typer.echo(
        f"run {short_id}  route={data.route}  principal={data.principal_id}"
        f"  status={data.status}  config={digest_display}"
    )
    typer.echo("─" * 72)

    verdict_events = [e for e in data.events if e.get("event_type") == "verdict"]

    if not verdict_events:
        typer.echo("  (no verdict events recorded)")
    else:
        for ev in verdict_events:
            stage = ev.get("stage", "?")
            node = ev.get("node", "?")
            ev_data = _event_data(ev)
            # Every real verdict-emitting node (GuardNode, MCP tool guards,
            # RAG retrieval guards, the HITL resume path) keys the verdict
            # kind as "verdict" — "kind"/"status" are kept as fallbacks only.
            kind = str(ev_data.get("verdict", ev_data.get("kind", ev_data.get("status", "?"))))
            summary_parts = [
                f"{k}={v}" for k, v in ev_data.items() if k not in ("verdict", "kind", "status")
            ]
            summary = "  " + "  ".join(summary_parts) if summary_parts else ""
            typer.echo(f"  {stage:12s}  {node:24s}  {_colour_kind(kind)}{summary}")

    typer.echo("─" * 72)

    # Footer: short-circuit note when provider never called
    execute_completed = any(
        e.get("event_type") == "node_end" and "execute" in str(e.get("node", "")).lower()
        for e in data.events
    )
    if data.status in ("blocked", "denied") and not execute_completed:
        blocked_at = None
        for ev in verdict_events:
            ev_data = _event_data(ev)
            kind = str(ev_data.get("verdict", ev_data.get("kind", ""))).lower()
            if kind in ("block", "blocked", "denied"):
                blocked_at = f"{ev.get('stage')}/{ev.get('node')}"
                break
        if blocked_at:
            typer.echo(f"  short-circuited at {blocked_at} · provider never called")
