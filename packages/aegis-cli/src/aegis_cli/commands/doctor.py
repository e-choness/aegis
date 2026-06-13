"""CLI command: `aegis doctor` — environment health checks."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="doctor", invoke_without_command=True, help="Check Aegis environment health.")
_console = Console()
_err_console = Console(stderr=True)

_DEFAULT_CONFIG = Path("aegis.yaml")
_DEFAULT_PROVIDERS_STORE = Path.home() / ".aegis" / "providers.json"


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class HealthCheck:
    name: str
    status: CheckStatus
    detail: str


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_config(config_path: Path) -> HealthCheck:
    """AEG-CFG: aegis.yaml exists and is valid YAML."""
    if not config_path.exists():
        return HealthCheck(
            name="config",
            status=CheckStatus.FAIL,
            detail=f"{config_path} not found. Run `aegis init` to create one.",
        )
    try:
        import yaml

        with open(config_path) as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, (dict, type(None))):
            return HealthCheck(
                name="config",
                status=CheckStatus.FAIL,
                detail=f"{config_path} does not contain a YAML mapping.",
            )
    except Exception as exc:
        return HealthCheck(
            name="config",
            status=CheckStatus.FAIL,
            detail=f"{config_path} could not be parsed: {exc}",
        )
    return HealthCheck(name="config", status=CheckStatus.OK, detail=str(config_path))


def check_pii_extra() -> HealthCheck:
    """AEG-POL: presidio-analyzer (PII extra) is installed."""
    spec = None
    try:
        spec = importlib.util.find_spec("presidio_analyzer")
    except ModuleNotFoundError:
        pass
    if spec is None:
        return HealthCheck(
            name="pii_extra",
            status=CheckStatus.WARN,
            detail=(
                "presidio-analyzer not installed. "
                "Install aegis-pack-pii[pii] to enable PII masking."
            ),
        )
    return HealthCheck(name="pii_extra", status=CheckStatus.OK, detail="presidio-analyzer found.")


def check_rag_extra() -> HealthCheck:
    """AEG-RAG: chromadb (RAG extra) is installed."""
    spec = None
    try:
        spec = importlib.util.find_spec("chromadb")
    except ModuleNotFoundError:
        pass
    if spec is None:
        return HealthCheck(
            name="rag_extra",
            status=CheckStatus.WARN,
            detail=(
                "chromadb not installed. "
                "Install aegis-core[rag] to enable RAG retrieval."
            ),
        )
    return HealthCheck(name="rag_extra", status=CheckStatus.OK, detail="chromadb found.")


def check_provider_store(store_path: Path = _DEFAULT_PROVIDERS_STORE) -> HealthCheck:
    """AEG-PRV: provider profile store file exists."""
    if not store_path.exists():
        return HealthCheck(
            name="provider_store",
            status=CheckStatus.WARN,
            detail=(
                f"{store_path} not found. "
                "Run `aegis provider add` to create a provider profile."
            ),
        )
    return HealthCheck(
        name="provider_store",
        status=CheckStatus.OK,
        detail=str(store_path),
    )


def check_providers_reachable(store_path: Path = _DEFAULT_PROVIDERS_STORE) -> HealthCheck:
    """AEG-PRV: ping each provider in the store (opt-in)."""
    if not store_path.exists():
        return HealthCheck(
            name="providers_reachable",
            status=CheckStatus.WARN,
            detail="No provider store found; skipping reachability check.",
        )
    try:
        import json

        with open(store_path) as f:
            data = json.load(f)
        profiles = data if isinstance(data, list) else []
        if not profiles:
            return HealthCheck(
                name="providers_reachable",
                status=CheckStatus.WARN,
                detail="No provider profiles configured.",
            )
        # Best-effort TCP reachability for each profile with a base_url
        import socket
        import urllib.parse

        unreachable: list[str] = []
        for profile in profiles:
            base_url = profile.get("base_url")
            if not base_url:
                continue
            parsed = urllib.parse.urlparse(base_url)
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                with socket.create_connection((host, port), timeout=3):
                    pass
            except OSError:
                unreachable.append(profile.get("name", host))

        if unreachable:
            return HealthCheck(
                name="providers_reachable",
                status=CheckStatus.FAIL,
                detail=f"Unreachable: {', '.join(unreachable)}",
            )
        return HealthCheck(
            name="providers_reachable",
            status=CheckStatus.OK,
            detail=f"All {len(profiles)} provider(s) reachable.",
        )
    except Exception as exc:
        return HealthCheck(
            name="providers_reachable",
            status=CheckStatus.FAIL,
            detail=f"Check failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Public helper for tests
# ---------------------------------------------------------------------------


def run_checks(
    config_path: Path = _DEFAULT_CONFIG,
    store_path: Path = _DEFAULT_PROVIDERS_STORE,
    check_providers: bool = False,
) -> list[HealthCheck]:
    """Run all health checks and return the results."""
    checks: list[HealthCheck] = [
        check_config(config_path),
        check_pii_extra(),
        check_rag_extra(),
        check_provider_store(store_path),
    ]
    if check_providers:
        checks.append(check_providers_reachable(store_path))
    return checks


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def doctor(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to aegis.yaml to validate."),
    ] = _DEFAULT_CONFIG,
    store_path: Annotated[
        Path,
        typer.Option("--store", help="Path to provider profile store."),
    ] = _DEFAULT_PROVIDERS_STORE,
    check_providers: Annotated[
        bool,
        typer.Option("--check-providers", help="Ping each configured provider (opt-in)."),
    ] = False,
) -> None:
    """Check Aegis environment health (config, extras, provider store)."""
    checks = run_checks(config_path, store_path, check_providers)

    table = Table(title="Aegis Doctor", show_header=True, header_style="bold cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")

    any_fail = False
    for check in checks:
        if check.status == CheckStatus.OK:
            status_str = "[green]OK[/green]"
        elif check.status == CheckStatus.WARN:
            status_str = "[yellow]WARN[/yellow]"
        else:
            status_str = "[red]FAIL[/red]"
            any_fail = True
        table.add_row(check.name, status_str, check.detail)

    _console.print(table)

    if any_fail:
        raise typer.Exit(1)
