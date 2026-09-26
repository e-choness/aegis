"""CLI commands: `aegis policy lint` and `aegis policy test`."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from aegis_core.errors import AegisPluginNotFoundError
from aegis_core.guardrails import GuardNode, RegexGuard
from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.assembler import PipelineAssembler
from aegis_core.pipeline.state import RunState
from aegis_core.providers.models import Message
from aegis_core.registry import PluginRegistry
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
    - AEG-POL-003: a non-incremental egress guard forces a route to buffer.
    - AEG-POL-004: a stage ``aegis serve`` cannot enforce yet (tool_call/tool_result).
    - AEG-POL-005: a provider's endpoint URL encodes a region that contradicts
      its declared ``residency.region`` (needs the residency pack installed).
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

    # AEG-POL-002: each guardrail pack must be discoverable under the
    # aegis.packs entry-point group (the same lookup build_executor() does —
    # a pack name like "aegis.pii" is a registry key, not a Python module
    # path, so importlib.util.find_spec() would never find it).
    registry = PluginRegistry()
    registry.discover(groups=("aegis.packs",))
    for guard_name, guard_cfg in guardrails_section.items():
        if not isinstance(guard_cfg, dict):
            continue
        pack: str | None = guard_cfg.get("pack")
        if not pack:
            continue
        try:
            registry.get(pack, "aegis.packs")
        except AegisPluginNotFoundError:
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

    # AEG-POL-003: egress guards that are non-incremental force a streaming downgrade.
    # Check both global pipeline.egress and per-route pipeline.egress.
    def _check_streaming_downgrade(egress_refs: list, location: str) -> None:
        for ref in egress_refs:
            base = str(ref).split(".")[0]
            guard_cfg = guardrails_section.get(base) or {}
            guard_streaming = guard_cfg.get("streaming", "none") if isinstance(guard_cfg, dict) else "none"
            if guard_streaming != "incremental":
                issues.append(LintIssue(
                    code="AEG-POL-003",
                    message=(
                        f"Egress guard {ref!r} has streaming={guard_streaming!r}; "
                        f"this route will buffer responses instead of true-streaming."
                    ),
                    location=location,
                ))

    _check_streaming_downgrade(
        pipeline_section.get("egress") or [] if isinstance(pipeline_section, dict) else [],
        "pipeline.egress",
    )
    for route_name, route_cfg in routes_section.items():
        if not isinstance(route_cfg, dict):
            continue
        route_pipeline = route_cfg.get("pipeline") or {}
        if isinstance(route_pipeline, dict):
            _check_streaming_downgrade(
                route_pipeline.get("egress") or [],
                f"routes.{route_name}.pipeline.egress",
            )

    # AEG-POL-004: stages aegis serve refuses to start with (it can't enforce them).
    from aegis_core.config.build import UNWIRED_STAGES

    stage_sections: list[tuple[str, Any]] = [("pipeline", pipeline_section)] + [
        (f"routes.{rname}.pipeline", (rcfg or {}).get("pipeline") if isinstance(rcfg, dict) else None)
        for rname, rcfg in routes_section.items()
    ]
    for location, section in stage_sections:
        if not isinstance(section, dict):
            continue
        for stage in UNWIRED_STAGES:
            if section.get(stage):
                issues.append(LintIssue(
                    code="AEG-POL-004",
                    message=(
                        f"{stage} stage is not enforced by aegis serve yet; the server "
                        "will refuse to start. Configure tool governance in Python "
                        "(aegis_core.mcp.McpExecuteNode) and remove this key."
                    ),
                    location=f"{location}.{stage}",
                ))

    # AEG-POL-005: declared residency vs. region encoded in the endpoint URL.
    issues.extend(_lint_residency_endpoints(raw.get("providers") or {}))

    return issues


def _lint_residency_endpoints(providers: dict) -> list[LintIssue]:
    try:
        from aegis_pack_residency.lint import lint_endpoint
        from aegis_pack_residency.schema import ResidencyProfile
    except ImportError:  # residency pack not installed — nothing to check against
        return []

    issues: list[LintIssue] = []
    for pname, pcfg in providers.items():
        if not isinstance(pcfg, dict):
            continue
        residency = pcfg.get("residency")
        base_url = pcfg.get("base_url")
        if not isinstance(residency, dict) or not residency.get("region") or not base_url:
            continue
        profile = ResidencyProfile(
            region=str(residency["region"]),
            jurisdiction=str(residency.get("jurisdiction") or "unspecified"),
            endpoint_url=str(base_url),
        )
        for violation in lint_endpoint(profile):
            issues.append(LintIssue(
                code="AEG-POL-005",
                message=(
                    f"endpoint region '{violation.detected}' ({violation.provider}) does not "
                    f"match declared residency.region '{violation.declared}'"
                ),
                location=f"providers.{pname}.residency.region",
            ))
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
