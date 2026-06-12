"""CLI commands: `aegis policy lint` and `aegis policy test`."""

from __future__ import annotations

import asyncio
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.table import Table

from aegis_core.guardrails import GuardNode, RegexGuard
from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.assembler import PipelineAssembler
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_core.testing.providers import FakeProvider

app = typer.Typer(name="policy", help="Lint and test Aegis policy configurations.")
_console = Console()
_err_console = Console(stderr=True, style="bold red")

_DEFAULT_CONFIG = Path("aegis.yaml")


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


@dataclass
class LintIssue:
    code: str
    message: str
    location: str


def lint_policy(config_path: Path) -> list[LintIssue]:
    """Lint an aegis.yaml for policy issues without Pydantic validation.

    Checks:
    - AEG-POL-001: pipeline references an undeclared guardrail name.
    - AEG-POL-002: guardrail pack module is not importable.
    """
    issues: list[LintIssue] = []

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
    except Exception as exc:
        issues.append(LintIssue(
            code="AEG-POL-000",
            message=f"Failed to parse YAML: {exc}",
            location=str(config_path),
        ))
        return issues

    if not isinstance(raw, dict):
        return issues

    guardrails_section: dict = raw.get("guardrails") or {}

    # AEG-POL-002: each guardrail pack must be importable
    for guard_name, guard_cfg in guardrails_section.items():
        if not isinstance(guard_cfg, dict):
            continue
        pack: str | None = guard_cfg.get("pack")
        try:
            spec = importlib.util.find_spec(pack) if pack else None
        except ModuleNotFoundError:
            spec = None
        if pack and spec is None:
            issues.append(LintIssue(
                code="AEG-POL-002",
                message=f"Guardrail pack {pack!r} is not installed.",
                location=f"guardrails.{guard_name}.pack",
            ))

    # AEG-POL-001: pipeline refs must exist in guardrails section
    def _check_refs(refs: list, location: str) -> None:
        for ref in refs:
            base = str(ref).split(".")[0]
            if base not in guardrails_section:
                issues.append(LintIssue(
                    code="AEG-POL-001",
                    message=(
                        f"Pipeline references unknown guardrail {ref!r}. "
                        f"Declared: {list(guardrails_section)}"
                    ),
                    location=location,
                ))

    pipeline_section: dict = raw.get("pipeline") or {}
    if isinstance(pipeline_section, dict):
        for stage in ("ingress", "tool_call", "tool_result", "egress"):
            _check_refs(pipeline_section.get(stage) or [], f"pipeline.{stage}")

    routes_section: dict = raw.get("routes") or {}
    for route_name, route_cfg in routes_section.items():
        if not isinstance(route_cfg, dict):
            continue
        route_pipeline: dict = route_cfg.get("pipeline") or {}
        if isinstance(route_pipeline, dict):
            for stage in ("ingress", "tool_call", "tool_result", "egress"):
                _check_refs(
                    route_pipeline.get(stage) or [],
                    f"routes.{route_name}.pipeline.{stage}",
                )

    return issues


# ---------------------------------------------------------------------------
# Fixture runner
# ---------------------------------------------------------------------------


def _make_guard(cfg: dict) -> Guardrail:
    guard_type = cfg.get("type", "regex")
    if guard_type == "regex":
        return RegexGuard(
            patterns=cfg.get("patterns") or [],
            reason=cfg.get("reason", "blocked by policy"),
            name=cfg.get("name", "regex"),
        )
    raise ValueError(f"Unknown guard type: {guard_type!r}")


async def _run_one_fixture(fixture_path: Path) -> dict:
    with open(fixture_path) as f:
        fixture = yaml.safe_load(f)

    guards = [_make_guard(g) for g in fixture.get("guards") or []]
    guard_node = GuardNode(guards)
    fake = FakeProvider()
    pipeline = PipelineAssembler().compile(ingress=[guard_node], provider=fake)

    state = RunState(
        run_id="fixture-test",
        route="default",
        messages=[Message(role="user", content=fixture.get("input") or "")],
    )
    result = await pipeline.run(state)

    expected = fixture.get("expected", "allow")
    actual_status = result.status

    if expected == "block":
        passed = actual_status == "blocked" and len(fake.complete_calls) == 0
    else:
        # allow or sanitize — pipeline must not be blocked/paused
        passed = actual_status not in ("blocked", "paused")

    return {
        "fixture": fixture_path.name,
        "description": fixture.get("description") or "",
        "expected": expected,
        "actual": actual_status,
        "passed": passed,
        "error": None,
    }


async def _run_all_fixtures(fixture_files: list[Path]) -> list[dict]:
    results = []
    for fixture_path in fixture_files:
        try:
            r = await _run_one_fixture(fixture_path)
        except Exception as exc:
            r = {
                "fixture": fixture_path.name,
                "description": "",
                "expected": "",
                "actual": "error",
                "passed": False,
                "error": str(exc),
            }
        results.append(r)
    return results


def run_fixture_tests(fixtures_dir: Path) -> list[dict]:
    """Run all YAML fixture files in *fixtures_dir* through the guard pipeline.

    Offline — zero model calls. Each fixture is run through a
    :class:`~aegis_core.guardrails.spine.GuardNode` backed by a
    :class:`~aegis_core.testing.providers.FakeProvider`.
    """
    fixture_files = sorted(fixtures_dir.glob("*.yaml"))
    if not fixture_files:
        return []
    return asyncio.run(_run_all_fixtures(fixture_files))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("lint")
def lint(
    config_path: Annotated[
        Path,
        typer.Argument(help="Path to aegis.yaml to lint."),
    ] = _DEFAULT_CONFIG,
) -> None:
    """Lint an aegis.yaml for policy issues (broken refs, missing packs)."""
    issues = lint_policy(config_path)
    if not issues:
        _console.print(f"[green]✓[/green] {config_path}: no issues found.")
        return

    for issue in issues:
        _console.print(
            f"[red]{issue.code}[/red] [{issue.location}] {issue.message}",
            markup=True,
        )
    raise typer.Exit(1)


@app.command("test")
def run_tests(
    fixtures_dir: Annotated[
        Path,
        typer.Argument(help="Directory containing fixture YAML files."),
    ],
) -> None:
    """Run policy fixture tests offline (zero model calls)."""
    results = run_fixture_tests(fixtures_dir)

    if not results:
        _console.print("[yellow]No fixtures found.[/yellow]")
        return

    table = Table(title="Policy Fixture Results")
    table.add_column("Fixture", style="cyan")
    table.add_column("Description")
    table.add_column("Expected", style="blue")
    table.add_column("Actual", style="blue")
    table.add_column("Status", style="bold")

    all_passed = True
    for r in results:
        status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        if not r["passed"]:
            all_passed = False
        table.add_row(
            r["fixture"],
            r["description"],
            r["expected"],
            r["actual"],
            status,
        )

    _console.print(table)

    if not all_passed:
        raise typer.Exit(1)
