"""Scaffold helper — emits a publishable plugin package skeleton."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

_VALID_KINDS = ("guardrail", "provider")


def _to_pascal(name: str) -> str:
    """Convert kebab-case or snake_case name to PascalCase."""
    return "".join(word.capitalize() for word in re.split(r"[-_]", name))


def _to_snake(name: str) -> str:
    """Convert kebab-case name to snake_case."""
    return name.replace("-", "_")


# ---------------------------------------------------------------------------
# File templates
# ---------------------------------------------------------------------------


def _guardrail_pyproject(pkg_name: str, module_name: str, guard_name: str) -> str:
    return dedent(f"""\
        [project]
        name = "{pkg_name}"
        version = "0.1.0"
        description = "Aegis guardrail plugin — {guard_name}."
        license = {{ text = "MIT" }}
        requires-python = ">=3.12"
        dependencies = ["aegis-core>=2.0.0a0"]

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["src/{module_name}"]

        [project.entry-points."aegis.guardrails"]
        {_to_snake(guard_name.lower())} = "{module_name}:{guard_name}"
    """)


def _provider_pyproject(pkg_name: str, module_name: str, provider_name: str) -> str:
    return dedent(f"""\
        [project]
        name = "{pkg_name}"
        version = "0.1.0"
        description = "Aegis provider plugin — {provider_name}."
        license = {{ text = "MIT" }}
        requires-python = ">=3.12"
        dependencies = ["aegis-core>=2.0.0a0"]

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["src/{module_name}"]

        [project.entry-points."aegis.providers"]
        {_to_snake(provider_name.lower())} = "{module_name}:{provider_name}"
    """)


def _guardrail_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis guardrail plugin — {class_name}.\"\"\"

        from {module_name}.guard import {class_name}

        __all__ = ["{class_name}"]
    """)


def _guardrail_impl(class_name: str, guard_name_lower: str) -> str:
    return dedent(f"""\
        \"\"\"Guardrail implementation for {class_name}.\"\"\"

        from __future__ import annotations

        from typing import ClassVar, Literal

        from aegis_core.pipeline.state import RunState
        from aegis_core.pipeline.verdict import Verdict


        class {class_name}:
            \"\"\"Stub guardrail — replace the scan body with real logic.\"\"\"

            name: str = "{guard_name_lower}"
            streaming: ClassVar[Literal["none", "incremental"]] = "none"

            async def scan(self, state: RunState) -> Verdict:
                \"\"\"Scan *state* and return a Verdict.

                This stub always allows.  Implement your detection logic here
                and return ``Verdict.block(reason=...)`` when content is unsafe.
                \"\"\"
                return Verdict.allow()
    """)


def _provider_init(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Aegis provider plugin — {class_name}.\"\"\"

        from {module_name}.provider import {class_name}

        __all__ = ["{class_name}"]
    """)


def _provider_impl(class_name: str, provider_name_lower: str) -> str:
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

            name: str = "{provider_name_lower}"

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
                    provider_type="{provider_name_lower}",
                    models=["stub-model"],
                    residency=ResidencyInfo(),
                    supports_streaming=True,
                    supports_embeddings=True,
                )
    """)


def _guardrail_contract_test(module_name: str, class_name: str) -> str:
    return dedent(f"""\
        \"\"\"Contract-kit test — validates the {class_name} guardrail contract.

        Run with:  pytest tests/test_contract.py -v
        \"\"\"

        import asyncio

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


def _conftest(src_rel: str = "src") -> str:
    return dedent(f"""\
        \"\"\"Add src/ to sys.path so tests can import the local package.\"\"\"

        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent / "{src_rel}"))
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
        kind: Plugin kind — ``"guardrail"`` or ``"provider"``.
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

    # Create directories
    src_pkg.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    # conftest.py and pytest.ini at package root
    (pkg_root / "conftest.py").write_text(_conftest())
    (pkg_root / "pytest.ini").write_text(_pytest_ini())
    (tests_dir / "__init__.py").write_text("")

    if kind == "guardrail":
        (pkg_root / "pyproject.toml").write_text(
            _guardrail_pyproject(pkg_name, module_name, class_name)
        )
        (src_pkg / "__init__.py").write_text(_guardrail_init(module_name, class_name))
        (src_pkg / "guard.py").write_text(_guardrail_impl(class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(
            _guardrail_contract_test(module_name, class_name)
        )
    else:  # provider
        (pkg_root / "pyproject.toml").write_text(
            _provider_pyproject(pkg_name, module_name, class_name)
        )
        (src_pkg / "__init__.py").write_text(_provider_init(module_name, class_name))
        (src_pkg / "provider.py").write_text(_provider_impl(class_name, name_lower))
        (tests_dir / "test_contract.py").write_text(
            _provider_contract_test(module_name, class_name)
        )

    return pkg_root
