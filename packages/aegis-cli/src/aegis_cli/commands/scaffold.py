"""Scaffold helper — emits a publishable plugin package skeleton (Phase 3)."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

_VALID_KINDS = ("guardrail", "node", "provider", "exporter")

#: Entry-point group each kind registers its primary class under.
_ENTRY_POINT_GROUP = {
    "guardrail": "aegis.guardrails",
    "node": "aegis.nodes",
    "provider": "aegis.providers",
    "exporter": "aegis.exporters",
}

#: Kinds that can be declared in a route's ``guardrails:`` YAML section and
#: therefore need a ``from_config`` factory under the ``aegis.packs`` group
#: (PROJECT_SPEC Phase 0 convention).
_HAS_PACK_FACTORY = ("guardrail", "node")


def _to_pascal(name: str) -> str:
    """Convert kebab-case or snake_case name to PascalCase."""
    return "".join(word.capitalize() for word in re.split(r"[-_]", name))


def _to_snake(name: str) -> str:
    """Convert kebab-case name to snake_case."""
    return name.replace("-", "_")


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def _pyproject(kind: str, pkg_name: str, module_name: str, name_lower: str) -> str:
    from aegis_core import __version__ as core_version

    group = _ENTRY_POINT_GROUP[kind]
    class_name = _to_pascal(name_lower)
    body = dedent(f"""\
        [project]
        name = "{pkg_name}"
        version = "0.1.0"
        description = "Aegis {kind} plugin — {class_name}."
        license = {{ text = "MIT" }}
        requires-python = ">=3.12"
        dependencies = ["aegis-gateway-core>={core_version}"]

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["src/{module_name}"]

        [project.entry-points."{group}"]
        {name_lower} = "{module_name}:{class_name}"
        """)
    if kind in _HAS_PACK_FACTORY:
        body += dedent(f"""
            [project.entry-points."aegis.packs"]
            "aegis.{name_lower}" = "{module_name}.factory:from_config"
            """)
    return body


# ---------------------------------------------------------------------------
# Implementation stubs, per kind
# ---------------------------------------------------------------------------


def _guardrail_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis guardrail plugin — {class_name}.\"\"\"

        from {module_name}.guard import {class_name}

        __all__ = ["{class_name}"]
    """)


def _guardrail_impl(class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Guardrail implementation for {class_name}.\"\"\"

        from __future__ import annotations

        from typing import ClassVar, Literal

        from aegis_core.pipeline.state import RunState
        from aegis_core.pipeline.verdict import Verdict


        class {class_name}:
            \"\"\"Stub guardrail — replace the scan body with real logic.\"\"\"

            name: str = "{name_lower}"
            streaming: ClassVar[Literal["none", "incremental"]] = "none"

            async def scan(self, state: RunState) -> Verdict:
                \"\"\"Scan *state* and return a Verdict.

                This stub always allows.  Implement your detection logic here
                and return ``Verdict.block(reason=...)`` when content is unsafe.
                \"\"\"
                return Verdict.allow()
    """)


def _node_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis pipeline node plugin — {class_name}.\"\"\"

        from {module_name}.node import {class_name}

        __all__ = ["{class_name}"]
    """)


def _node_impl(class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"PipelineNode implementation for {class_name}.\"\"\"

        from __future__ import annotations

        from dataclasses import dataclass

        from aegis_core.pipeline.state import RunState, RunStateDelta


        @dataclass
        class {class_name}:
            \"\"\"Stub node — replace the run body with real logic.

            ``name`` defaults to ``"{name_lower}"`` but can be overridden per
            declaration, e.g. ``{class_name}(name=f"{{route_guardrail_name}}.mask")``
            so ``from_config`` can namespace multiple instances of this node.
            \"\"\"

            name: str = "{name_lower}"

            async def run(self, state: RunState) -> RunStateDelta:
                \"\"\"Return a partial state update for *state*.

                This stub is a no-op pass-through.  Emit a
                ``RunEvent(stage=..., node=self.name, event_type="verdict", data=...)``
                if your node should show up in ``aegis explain`` and the
                evidence ledger.
                \"\"\"
                return RunStateDelta()
    """)


def _provider_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis provider plugin — {class_name}.\"\"\"

        from {module_name}.provider import {class_name}

        __all__ = ["{class_name}"]
    """)


def _provider_impl(class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Provider implementation for {class_name}.\"\"\"

        from __future__ import annotations

        from collections.abc import AsyncIterator

        from aegis_core.providers.models import (
            Chunk,
            CompletionRequest,
            CompletionResult,
            ProviderInfo,
            ResidencyInfo,
            UsageInfo,
        )


        class {class_name}:
            \"\"\"Stub provider — replace each method body with real logic.\"\"\"

            name: str = "{name_lower}"

            async def complete(self, req: CompletionRequest) -> CompletionResult:
                \"\"\"Return a completion for *req*.  Replace with real API call.\"\"\"
                return CompletionResult(
                    text="Hello from {class_name}!",
                    model=req.model or "stub-model",
                    usage=UsageInfo(
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                    ),
                    finish_reason="stop",
                )

            async def stream(self, req: CompletionRequest) -> AsyncIterator[Chunk]:
                \"\"\"Yield token chunks for *req*.  Replace with real streaming call.\"\"\"

                async def _gen() -> AsyncIterator[Chunk]:
                    yield Chunk(text="Hello", finish_reason=None)
                    yield Chunk(text=" from {class_name}!", finish_reason="stop")

                return _gen()

            async def embed(self, texts: list[str]) -> list[list[float]]:
                \"\"\"Return one embedding vector per text.  Replace with real call.\"\"\"
                return [[0.0] for _ in texts]

            def info(self) -> ProviderInfo:
                \"\"\"Return static provider metadata.\"\"\"
                return ProviderInfo(
                    name=self.name,
                    provider_type="{name_lower}",
                    models=["stub-model"],
                    residency=ResidencyInfo(),
                    supports_streaming=True,
                    supports_embeddings=True,
                )
    """)


def _exporter_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis exporter plugin — {class_name}.\"\"\"

        from {module_name}.exporter import {class_name}

        __all__ = ["{class_name}"]
    """)


def _exporter_impl(class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Exporter implementation for {class_name}.\"\"\"

        from __future__ import annotations


        class {class_name}:
            \"\"\"Stub exporter — replace export() with real delivery logic.

            *records* are already-redacted evidence-ledger records (see
            ``aegis_server.store.ledger``); this exporter must not perform
            any further redaction, only delivery.
            \"\"\"

            name: str = "{name_lower}"

            async def export(self, records: list[dict]) -> None:
                \"\"\"Deliver *records* to this exporter's destination.\"\"\"
    """)


# ---------------------------------------------------------------------------
# aegis.packs factory.py stub (guardrail + node kinds only)
# ---------------------------------------------------------------------------


def _guardrail_factory(module_name: str, class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Pack factory for aegis.{name_lower} — registered under aegis.packs.\"\"\"

        from __future__ import annotations

        from aegis_core.packs import GuardrailConfig
        from aegis_core.guardrails.spine import GuardNode
        from aegis_core.pipeline.protocol import PipelineNode

        from {module_name} import {class_name}


        def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
            \"\"\"Return the nodes this pack contributes, keyed by stage.

            This stub wires the guard into ingress only. A pack may
            contribute to several stages from one declaration — see
            ``aegis_pack_pii.factory`` for an ingress+egress example.
            \"\"\"
            return {{"ingress": [GuardNode([{class_name}()], name=name)]}}
    """)


def _node_factory(module_name: str, class_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Pack factory for aegis.{name_lower} — registered under aegis.packs.\"\"\"

        from __future__ import annotations

        from aegis_core.packs import GuardrailConfig
        from aegis_core.pipeline.protocol import PipelineNode

        from {module_name} import {class_name}


        def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
            \"\"\"Return the nodes this pack contributes, keyed by stage.\"\"\"
            return {{"ingress": [{class_name}(name=name)]}}
    """)


def _factory_test(module_name: str, name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Round-trip test for the aegis.packs factory.

        Run with:  pytest tests/test_factory.py -v
        \"\"\"

        from aegis_core.packs import GuardrailConfig
        from aegis_core.pipeline.protocol import PipelineNode

        from {module_name}.factory import from_config


        def test_from_config_returns_pipeline_nodes() -> None:
            cfg = GuardrailConfig(pack="aegis.{name_lower}")
            result = from_config("{name_lower}", cfg)
            assert isinstance(result, dict)
            assert result, "from_config() must contribute at least one stage"
            for nodes in result.values():
                for node in nodes:
                    assert isinstance(node, PipelineNode)


        def test_from_config_is_deterministic() -> None:
            cfg = GuardrailConfig(pack="aegis.{name_lower}")
            r1 = from_config("{name_lower}", cfg)
            r2 = from_config("{name_lower}", cfg)
            assert set(r1.keys()) == set(r2.keys())
    """)


# ---------------------------------------------------------------------------
# Contract-kit tests
# ---------------------------------------------------------------------------


def _guardrail_contract_test(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Contract-kit test — validates the {class_name} guardrail contract.

        Run with:  pytest tests/test_contract.py -v
        \"\"\"

        import pytest

        from aegis_core.testing.guardrails import GuardrailContractKit

        from {module_name} import {class_name}


        @pytest.fixture
        def guard() -> {class_name}:
            return {class_name}()


        def test_contract_sync(guard: {class_name}) -> None:
            \"\"\"Synchronous contract assertions pass with zero edits.\"\"\"
            kit = GuardrailContractKit(guard)
            kit.assert_all()


        async def test_contract_async(guard: {class_name}) -> None:
            \"\"\"Full async contract (including scan) passes with zero edits.\"\"\"
            kit = GuardrailContractKit(guard)
            await kit.assert_all_async()
    """)


def _node_contract_test(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Contract-kit test — validates the {class_name} node contract.

        Run with:  pytest tests/test_contract.py -v
        \"\"\"

        import pytest

        from aegis_core.testing.nodes import NodeContractKit

        from {module_name} import {class_name}


        @pytest.fixture
        def node() -> {class_name}:
            return {class_name}()


        def test_contract_sync(node: {class_name}) -> None:
            \"\"\"Synchronous contract assertions pass with zero edits.\"\"\"
            kit = NodeContractKit(node)
            kit.assert_all()


        async def test_contract_async(node: {class_name}) -> None:
            \"\"\"Full async contract (including run) passes with zero edits.\"\"\"
            kit = NodeContractKit(node)
            await kit.assert_all_async()
    """)


def _provider_contract_test(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Contract-kit test — validates the {class_name} provider contract.

        Run with:  pytest tests/test_contract.py -v
        \"\"\"

        import pytest

        from aegis_core.testing.providers import ProviderContractKit

        from {module_name} import {class_name}


        @pytest.fixture
        def provider() -> {class_name}:
            return {class_name}()


        def test_contract_sync(provider: {class_name}) -> None:
            \"\"\"Synchronous contract assertions pass with zero edits.\"\"\"
            kit = ProviderContractKit(provider)
            kit.assert_all()


        async def test_contract_async(provider: {class_name}) -> None:
            \"\"\"Full async contract passes with zero edits.\"\"\"
            kit = ProviderContractKit(provider)
            await kit.assert_all_async()
    """)


def _exporter_contract_test(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Contract-kit test — validates the {class_name} exporter contract.

        Run with:  pytest tests/test_contract.py -v
        \"\"\"

        import pytest

        from aegis_core.testing.exporters import ExporterContractKit

        from {module_name} import {class_name}


        @pytest.fixture
        def exporter() -> {class_name}:
            return {class_name}()


        def test_contract_sync(exporter: {class_name}) -> None:
            \"\"\"Synchronous contract assertions pass with zero edits.\"\"\"
            kit = ExporterContractKit(exporter)
            kit.assert_all()


        async def test_contract_async(exporter: {class_name}) -> None:
            \"\"\"Full async contract (including export) passes with zero edits.\"\"\"
            kit = ExporterContractKit(exporter)
            await kit.assert_all_async()
    """)


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------


def _conftest(src_rel: str = "src") -> str:
    return dedent(f"""\
        \"\"\"Add src/ to sys.path so tests can import the local package,
        and fail fast if aegis-core's contract-kit helpers are not importable.
        \"\"\"

        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent / "{src_rel}"))

        import aegis_core.testing  # noqa: F401
    """)


def _pytest_ini() -> str:
    return dedent("""\
        [pytest]
        asyncio_mode = auto
        addopts = -rN
    """)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold_plugin(
    kind: str,
    name: str,
    output_dir: Path = Path(".tmp"),
) -> Path:
    """Emit a publishable plugin package skeleton.

    Args:
        kind: Plugin kind — one of ``_VALID_KINDS``.
        name: Plugin name (kebab-case recommended, e.g. ``demo-guard``).
        output_dir: Parent directory for the scaffolded package.

    Returns:
        Path to the generated package root directory.

    Raises:
        ValueError: If *kind* is not one of the supported kinds.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"Unknown plugin kind {kind!r}. Valid kinds: {', '.join(_VALID_KINDS)}"
        )

    pkg_name = f"aegis-{kind}-{name}"
    module_name = f"aegis_{kind}_{_to_snake(name)}"
    class_name = _to_pascal(name)
    name_lower = _to_snake(name)

    pkg_root = output_dir / pkg_name
    src_pkg = pkg_root / "src" / module_name
    tests_dir = pkg_root / "tests"

    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    (pkg_root / "pyproject.toml").write_text(_pyproject(kind, pkg_name, module_name, name_lower))
    (pkg_root / "conftest.py").write_text(_conftest())
    (pkg_root / "pytest.ini").write_text(_pytest_ini())
    (tests_dir / "__init__.py").write_text("")

    if kind == "guardrail":
        (src_pkg / "__init__.py").write_text(_guardrail_init(module_name, class_name))
        (src_pkg / "guard.py").write_text(_guardrail_impl(class_name, name_lower))
        (src_pkg / "factory.py").write_text(_guardrail_factory(module_name, class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(_guardrail_contract_test(module_name, class_name))
        (tests_dir / "test_factory.py").write_text(_factory_test(module_name, name_lower))
    elif kind == "node":
        (src_pkg / "__init__.py").write_text(_node_init(module_name, class_name))
        (src_pkg / "node.py").write_text(_node_impl(class_name, name_lower))
        (src_pkg / "factory.py").write_text(_node_factory(module_name, class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(_node_contract_test(module_name, class_name))
        (tests_dir / "test_factory.py").write_text(_factory_test(module_name, name_lower))
    elif kind == "provider":
        (src_pkg / "__init__.py").write_text(_provider_init(module_name, class_name))
        (src_pkg / "provider.py").write_text(_provider_impl(class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(_provider_contract_test(module_name, class_name))
    else:  # exporter
        (src_pkg / "__init__.py").write_text(_exporter_init(module_name, class_name))
        (src_pkg / "exporter.py").write_text(_exporter_impl(class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(_exporter_contract_test(module_name, class_name))

    return pkg_root
