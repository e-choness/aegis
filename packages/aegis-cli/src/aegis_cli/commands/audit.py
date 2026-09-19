"""aegis audit — export, verify, and inspect the evidence ledger (Phase 2)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

from aegis_sdk import AegisClient

app = typer.Typer(help="Evidence ledger commands.", no_args_is_help=True)

_DEFAULT_URL = "http://localhost:8767"


def _base_url() -> str:
    return os.environ.get("AEGIS_SERVER_URL", _DEFAULT_URL).rstrip("/")


def _api_key() -> str:
    return os.environ.get("AEGIS_API_KEY", "")


def _make_client() -> AegisClient:
    return AegisClient(base_url=_base_url(), api_key=_api_key())


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _compute_hash(record_without_hash: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(record_without_hash).encode()).hexdigest()


@app.command("export")
def export_ledger(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)."),
    fmt: str = typer.Option("jsonl", "--format", "-f", help="Output format: jsonl or csv."),
    since_seq: int = typer.Option(0, "--since-seq", help="Return records with seq > N."),
    route: Optional[str] = typer.Option(None, "--route", help="Filter by route/model_id."),
) -> None:
    """Export evidence ledger records to JSONL or CSV."""
    try:
        with _make_client() as client:
            records = client.list_ledger(since_seq=since_seq, route=route)
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None

    out = open(output, "w", encoding="utf-8", newline="") if output else sys.stdout  # type: ignore[assignment]
    try:
        if fmt == "csv":
            if records:
                fieldnames = list(records[0].keys())
                writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for rec in records:
                    writer.writerow(rec)
        else:
            for rec in records:
                out.write(json.dumps(rec) + "\n")
    finally:
        if output:
            out.close()

    if output:
        typer.echo(f"Exported {len(records)} record(s) to {output}")


@app.command("verify")
def verify_chain(
    file: Path = typer.Argument(..., help="JSONL file to verify (one record per line)."),
) -> None:
    """Verify hash chain integrity of an exported JSONL ledger file."""
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        typer.echo(f"File not found: {file}", err=True)
        raise typer.Exit(1) from None

    records = []
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            typer.echo(f"Line {i}: invalid JSON — {exc}", err=True)
            raise typer.Exit(1) from None

    if not records:
        typer.echo("No records found in file.", err=True)
        raise typer.Exit(1)

    errors: list[str] = []
    prev_hash = "genesis"
    for rec in records:
        seq = rec.get("seq", "?")
        if rec.get("prev_hash") != prev_hash:
            errors.append(
                f"seq={seq}: prev_hash mismatch: expected {prev_hash!r}, got {rec.get('prev_hash')!r}"
            )
        rec_without_hash = {k: v for k, v in rec.items() if k != "hash"}
        expected = _compute_hash(rec_without_hash)
        if rec.get("hash") != expected:
            errors.append(
                f"seq={seq}: hash mismatch: expected {expected!r}, got {rec.get('hash')!r}"
            )
        prev_hash = rec.get("hash", "")

    if errors:
        for err in errors:
            typer.echo(f"  FAIL  {err}", err=True)
        typer.echo(f"\n{len(errors)} error(s) in {len(records)} records.", err=True)
        raise typer.Exit(1)

    typer.echo(f"OK  {len(records)} record(s) verified — chain is intact.")


@app.command("inventory")
def list_inventory(
    route: Optional[str] = typer.Option(None, "--route", help="Filter by route/model_id."),
    json_output: bool = typer.Option(False, "--json", help="Output raw records as JSON."),
) -> None:
    """List model inventory records from the evidence ledger."""
    try:
        with _make_client() as client:
            records = client.inventory_records(route=route)
    except httpx.ConnectError:
        typer.echo(f"Cannot connect to {_base_url()}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        typer.echo(f"Error {exc.response.status_code}: {exc.response.text}", err=True)
        raise typer.Exit(1) from None

    if json_output:
        typer.echo(json.dumps(records, indent=2))
        return

    if not records:
        typer.echo("No inventory records found.")
        return

    typer.echo(f"{'MODEL':30s}  {'VERSION':20s}  {'DEPLOYED':26s}  {'RISK':8s}  OWNER")
    typer.echo("─" * 100)
    for rec in records:
        model_id = str(rec.get("model_id", ""))[:30]
        version = str(rec.get("model_version") or "(none)")[:20]
        deployed = str(rec.get("date_of_deployment") or "")[:26]
        risk = str(rec.get("model_risk_rating") or "")[:8]
        owner = str(rec.get("model_owner") or "")
        typer.echo(f"{model_id:30s}  {version:20s}  {deployed:26s}  {risk:8s}  {owner}")
