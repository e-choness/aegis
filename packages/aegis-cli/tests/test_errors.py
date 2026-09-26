"""Error-code sweep — verifies AEG-* structure on all AegisError subclasses.

Also scans aegis-core source for bare raises of non-framework exceptions
and asserts the count is within the documented allowlist.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from aegis_core.errors import AegisError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AEG_CODE_RE = re.compile(r"^AEG-[A-Z]+-\d{3}$")


def _all_concrete_subclasses(cls: type) -> list[type]:
    """Recursively collect all non-abstract subclasses of *cls*."""
    result: list[type] = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_concrete_subclasses(sub))
    return result


# ---------------------------------------------------------------------------
# AEG-* structure tests
# ---------------------------------------------------------------------------


class TestAegisErrorStructure:
    """Every concrete AegisError subclass must carry proper AEG-* metadata."""

    @pytest.fixture(params=_all_concrete_subclasses(AegisError))
    def error_class(self, request: pytest.FixtureRequest) -> type:
        return request.param  # type: ignore[return-value]

    def test_has_code_attribute(self, error_class: type) -> None:
        assert hasattr(error_class, "code"), f"{error_class.__name__} missing 'code'"

    def test_code_matches_aeg_pattern(self, error_class: type) -> None:
        code: str = error_class.code  # type: ignore[attr-defined]
        assert _AEG_CODE_RE.match(code), (
            f"{error_class.__name__}.code={code!r} does not match AEG-AREA-NNN"
        )

    def test_has_what_attribute(self, error_class: type) -> None:
        assert hasattr(error_class, "what"), f"{error_class.__name__} missing 'what'"

    def test_what_is_non_empty(self, error_class: type) -> None:
        what: str = error_class.what  # type: ignore[attr-defined]
        assert isinstance(what, str), f"{error_class.__name__}.what must be a string"
        assert what, f"{error_class.__name__}.what must be non-empty"

    def test_has_why_attribute(self, error_class: type) -> None:
        assert hasattr(error_class, "why"), f"{error_class.__name__} missing 'why'"

    def test_why_is_non_empty(self, error_class: type) -> None:
        why: str = error_class.why  # type: ignore[attr-defined]
        assert isinstance(why, str), f"{error_class.__name__}.why must be a string"
        assert why, f"{error_class.__name__}.why must be non-empty"

    def test_has_fix_attribute(self, error_class: type) -> None:
        assert hasattr(error_class, "fix"), f"{error_class.__name__} missing 'fix'"

    def test_fix_is_non_empty(self, error_class: type) -> None:
        fix: str = error_class.fix  # type: ignore[attr-defined]
        assert isinstance(fix, str), f"{error_class.__name__}.fix must be a string"
        assert fix, f"{error_class.__name__}.fix must be non-empty"

    def test_instantiates_without_args(self, error_class: type) -> None:
        """AegisError subclasses must be instantiable with no arguments."""
        try:
            exc = error_class()
        except TypeError as e:
            pytest.fail(f"{error_class.__name__}() raised TypeError: {e}")
        assert isinstance(exc, AegisError)

    def test_str_contains_code(self, error_class: type) -> None:
        """str(exc) must include the AEG-* code."""
        exc = error_class()
        assert error_class.code in str(exc), (  # type: ignore[attr-defined]
            f"str({error_class.__name__}()) does not contain code {error_class.code!r}"
        )


# ---------------------------------------------------------------------------
# Bare-raise sweep
# ---------------------------------------------------------------------------

# These bare raises in aegis-core source are known and acceptable.
# Keyed by (relative_file, enclosing_scope, exception_name) — not line numbers,
# so unrelated edits above a raise don't break this test.
# If you add a new bare non-AEG raise, add it here and document why.
_KNOWN_BARE_RAISES: set[tuple[str, str, str]] = {
    # assembler.py: internal invariant guards (unreachable in practice)
    ("aegis_core/pipeline/assembler.py", "CompiledPipeline.resume", "RuntimeError"),
    ("aegis_core/pipeline/assembler.py", "PipelineAssembler.compile", "ValueError"),
    # executor.py: route lookup — callers translate KeyError into a 404
    ("aegis_core/pipeline/executor.py", "PipelineExecutor.get", "KeyError"),
    # profiles.py: duplicate profile name — data-layer boundary
    ("aegis_core/providers/profiles.py", "ProviderProfileStore.add", "ValueError"),
    # config/loader.py: missing PyYAML — import-time guard
    ("aegis_core/config/loader.py", "<module>", "ImportError"),
    # litellm_provider.py: _map_litellm_error() returns an AegisProviderError
    ("aegis_core/providers/litellm_provider.py", "LiteLLMProvider.complete", "_map_litellm_error"),
    ("aegis_core/providers/litellm_provider.py", "LiteLLMProvider.stream", "_map_litellm_error"),
    ("aegis_core/providers/litellm_provider.py", "LiteLLMProvider.embed", "_map_litellm_error"),
}

# Exception types that are always allowed (Python built-ins used for flow control)
_ALWAYS_ALLOWED = frozenset({"StopIteration", "StopAsyncIteration", "GeneratorExit"})

# Locate aegis-core source root relative to this test file
_CORE_SRC = (
    Path(__file__).parent.parent.parent  # packages/
    / "aegis-core" / "src"
)


def _exception_name(exc: ast.expr) -> str | None:
    func = exc.func if isinstance(exc, ast.Call) else exc
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _find_bare_raises(src_root: Path) -> list[tuple[str, str, str, int]]:
    """Walk Python source and return bare non-AEG raises.

    Returns:
        List of (relative_path, enclosing_scope, exception_name, lineno) tuples.
    """
    results: list[tuple[str, str, str, int]] = []

    def visit(node: ast.AST, rel: str, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            child_scope = scope
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                child_scope = f"{scope}.{child.name}" if scope else child.name
            if isinstance(child, ast.Raise) and child.exc is not None:
                name = _exception_name(child.exc)
                if name and not name.startswith("Aegis") and name not in _ALWAYS_ALLOWED:
                    results.append((rel, scope or "<module>", name, child.lineno))
            visit(child, rel, child_scope)

    for py_file in src_root.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        visit(tree, str(py_file.relative_to(src_root)).replace("\\", "/"), "")
    return results


class TestBareRaiseSweep:
    """Bare non-AEG raises in aegis-core must stay within the allowlist."""

    def test_no_new_bare_raises(self) -> None:
        """No new bare non-AEG raises may be added outside the allowlist."""
        if not _CORE_SRC.exists():
            pytest.skip(f"aegis-core source not found at {_CORE_SRC}")

        found = _find_bare_raises(_CORE_SRC)

        new_raises = [
            (rel, scope, name, lineno)
            for rel, scope, name, lineno in found
            if (rel, scope, name) not in _KNOWN_BARE_RAISES
        ]

        assert not new_raises, (
            "New bare non-AEG raises found in aegis-core. "
            "Either wrap them in an AegisError subclass or add to _KNOWN_BARE_RAISES:\n"
            + "\n".join(
                f"  {rel}:{lineno} ({scope})  raise {name}"
                for rel, scope, name, lineno in new_raises
            )
        )
