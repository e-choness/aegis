"""CLI commands: `aegis config validate` and `aegis config show`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax

from aegis_core.config import load_config
from aegis_core.errors import AegisConfigError

app = typer.Typer(name="config", help="Validate and inspect Aegis configuration.")
_console = Console()
_err_console = Console(stderr=True, style="bold red")

_DEFAULT_CONFIG = Path("aegis.yaml")


@app.command("validate")
def validate(
    config_path: Annotated[
        Path,
        typer.Argument(help="Path to aegis.yaml to validate."),
    ] = _DEFAULT_CONFIG,
) -> None:
    """Validate an aegis.yaml file and report any errors."""
    try:
        load_config(config_path)
    except AegisConfigError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc
    except Exception as exc:
        _err_console.print(f"Unexpected error: {exc}")
        raise typer.Exit(1) from exc

    _console.print(f"[green]✓[/green] {config_path} is valid.")


@app.command("show")
def show(
    config_path: Annotated[
        Path,
        typer.Argument(help="Path to aegis.yaml to display."),
    ] = _DEFAULT_CONFIG,
    output_format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: json or yaml."),
    ] = "json",
) -> None:
    """Load and display the resolved configuration (secrets redacted)."""
    try:
        cfg = load_config(config_path)
    except AegisConfigError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc
    except Exception as exc:
        _err_console.print(f"Unexpected error: {exc}")
        raise typer.Exit(1) from exc

    safe = cfg.safe_dict()

    if output_format == "yaml":
        try:
            import yaml  # type: ignore[import-untyped]

            text = yaml.dump(safe, default_flow_style=False, sort_keys=False)
            _console.print(Syntax(text, "yaml", theme="monokai"))
        except ImportError:
            _err_console.print("PyYAML is required for YAML output.")
            raise typer.Exit(1) from None
    else:
        text = json.dumps(safe, indent=2, default=str)
        _console.print(Syntax(text, "json", theme="monokai"))
