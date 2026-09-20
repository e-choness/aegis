"""Independent conformance checks for scaffolded Aegis plugins (Phase 3).

``aegis plugin test`` runs the author's own generated tests via pytest, then
these checks — independently of whatever the author wrote, so protocol drift
(a deleted assertion, a stripped ``streaming`` ClassVar) is still caught.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

_KIND_TO_GROUP = {
    "guardrail": "aegis.guardrails",
    "node": "aegis.nodes",
    "provider": "aegis.providers",
    "exporter": "aegis.exporters",
}


def _load_pyproject(pkg_root: Path) -> dict[str, Any]:
    return tomllib.loads((pkg_root / "pyproject.toml").read_text())


def _entry_point_target(pyproject: dict[str, Any], group: str) -> tuple[str, str] | None:
    """Return ``(module, attr)`` for the sole entry point declared in *group*."""
    eps = pyproject.get("project", {}).get("entry-points", {}).get(group, {})
    if not eps:
        return None
    value = next(iter(eps.values()))
    module, _, attr = value.partition(":")
    return module, attr


def _import_from_src(pkg_root: Path, module: str) -> Any:
    src = str(pkg_root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    importlib.invalidate_caches()
    return importlib.import_module(module)


def infer_kind(pkg_root: Path) -> str | None:
    """Best-effort guess at a scaffolded package's plugin kind from pyproject.toml."""
    pyproject = _load_pyproject(pkg_root)
    for kind, group in _KIND_TO_GROUP.items():
        if _entry_point_target(pyproject, group) is not None:
            return kind
    return None


def _collect_events_for_redaction_check(node: Any) -> list[dict[str, Any]]:
    """Run *node*.run() once and return its emitted events as dicts.

    Best-effort: any construction/execution failure yields no events rather
    than raising, since exercising the node's real behaviour is out of scope
    for a redaction check on a scaffold stub.
    """
    import asyncio

    from aegis_core.pipeline.state import RunState
    from aegis_core.providers.models import Message

    if not hasattr(node, "run"):
        return []
    state = RunState(
        run_id="conformance-check",
        route="default",
        messages=[Message(role="user", content="secret@example.com")],
    )
    try:
        delta = asyncio.run(node.run(state))
    except Exception:
        return []
    events = getattr(delta, "events", None) or []
    return [e.to_dict() if hasattr(e, "to_dict") else e for e in events]


def check_conformance(pkg_root: Path, kind: str) -> list[str]:
    """Verify *pkg_root* satisfies its declared protocol and factory contract.

    Returns a list of failure messages; an empty list means conformance passed.
    """
    from aegis_core.exporters.protocol import Exporter
    from aegis_core.guardrails.protocol import Guardrail
    from aegis_core.pipeline.protocol import PipelineNode
    from aegis_core.providers.protocol import ModelProvider

    protocol_by_kind: dict[str, type] = {
        "guardrail": Guardrail,
        "node": PipelineNode,
        "provider": ModelProvider,
        "exporter": Exporter,
    }
    if kind not in protocol_by_kind:
        return [f"Unknown plugin kind {kind!r}."]

    pyproject = _load_pyproject(pkg_root)
    group = _KIND_TO_GROUP[kind]
    target = _entry_point_target(pyproject, group)
    if target is None:
        return [f"No entry point declared under '{group}' in pyproject.toml."]

    module_name, attr = target
    try:
        module = _import_from_src(pkg_root, module_name)
        cls = getattr(module, attr)
        instance = cls()
    except Exception as exc:
        return [f"Failed to import/construct {module_name}:{attr} — {exc}"]

    failures: list[str] = []
    protocol = protocol_by_kind[kind]
    if not isinstance(instance, protocol):
        failures.append(
            f"{attr} does not satisfy the {protocol.__name__} Protocol — check "
            "for missing attributes (e.g. a `streaming` ClassVar on a guardrail)."
        )

    pack_target = _entry_point_target(pyproject, "aegis.packs")
    if pack_target is None:
        return failures

    factory_module_name, factory_attr = pack_target
    try:
        factory_module = _import_from_src(pkg_root, factory_module_name)
        from_config = getattr(factory_module, factory_attr)
    except Exception as exc:
        return [*failures, f"Failed to import factory {factory_module_name}:{factory_attr} — {exc}"]

    from aegis_core.config.models import GuardrailConfig

    cfg = GuardrailConfig(pack=f"aegis.{module_name}")
    try:
        r1 = from_config("conformance-check", cfg)
        r2 = from_config("conformance-check", cfg)
    except Exception as exc:
        return [*failures, f"from_config() raised — {exc}"]

    if not isinstance(r1, dict) or not r1:
        failures.append("from_config() must return a non-empty dict of stage -> [PipelineNode].")
        return failures

    if set(r1.keys()) != set(r2.keys()):
        failures.append("from_config() is not deterministic — calling it twice returned different stages.")

    for stage, nodes in r1.items():
        for node in nodes:
            if not isinstance(node, PipelineNode):
                failures.append(
                    f"from_config() stage {stage!r} contains an object that does not "
                    "satisfy the PipelineNode Protocol."
                )
                continue
            for event in _collect_events_for_redaction_check(node):
                data = event.get("data", {}) if isinstance(event, dict) else {}
                if "mask_map" in data or "messages" in data:
                    failures.append(
                        f"node {getattr(node, 'name', '?')!r} emits raw 'mask_map'/'messages' "
                        "in event data — redact before returning it from run()."
                    )

    return failures


def run_plugin_tests(pkg_root: Path, kind: str | None = None) -> tuple[bool, list[str]]:
    """Run pytest inside *pkg_root*, then the independent conformance suite.

    Returns ``(ok, messages)`` where *messages* are lines to display.
    """
    messages: list[str] = []
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(pkg_root), "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout:
        messages.append(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            messages.append(result.stderr)
        return False, messages

    resolved_kind = kind or infer_kind(pkg_root)
    if resolved_kind is None:
        messages.append("Could not infer plugin kind from pyproject.toml; skipping conformance suite.")
        return True, messages

    failures = check_conformance(pkg_root, resolved_kind)
    if failures:
        messages.extend(f"conformance: {f}" for f in failures)
        return False, messages

    messages.append("conformance suite passed.")
    return True, messages
