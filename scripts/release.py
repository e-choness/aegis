"""Release helper — one version for every published package.

Usage (inside the dev container)::

    uv run python scripts/release.py bump 2.0.0a1   # rewrite versions + internal pins
    uv run python scripts/release.py check v2.0.0a1  # CI: tag must match the files
    uv run python scripts/release.py packages        # paths of publishable packages
    uv run python scripts/release.py notes v2.0.0a1  # this version's CHANGELOG section

Every publishable package shares one version. Internal dependencies are pinned
to it exactly (``aegis-gateway-core==2.0.0a1``) so ``pip install
aegis-gateway==X`` can never mix components from different releases. The
TypeScript SDK's ``package.json`` follows along in semver form (``2.0.0-alpha.1``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent

#: Everything uploaded to PyPI, in dependency order. The test fixture plugin
#: under packages/ is deliberately absent — it must never be published.
PUBLISHED = [
    "packages/aegis-core",
    "packages/aegis-server",
    "sdk/python",
    "packages/aegis-cli",
    "packages/aegis-pack-pii",
    "packages/aegis-pack-llm-guard",
    "packages/aegis-pack-classification",
    "packages/aegis-pack-residency",
    "packages/aegis-pack-budgets",
    "packages/aegis-gateway",
]
TS_PACKAGE = ROOT / "sdk" / "typescript" / "package.json"

_VERSION_LINE = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)
_DEPS_BLOCK = re.compile(r"^dependencies = \[.*?\]$", re.MULTILINE | re.DOTALL)
# "aegis-gateway-core", "aegis-gateway-core==2.0.0a0", "aegis-gateway-pack-pii[pii]>=1"
_INTERNAL_DEP = re.compile(r'"(aegis-gateway(?:-[a-z-]+)?)(\[[a-z-]+\])?(?:[=<>!~][^"]*)?"')


def _pyprojects() -> list[Path]:
    return [ROOT / p / "pyproject.toml" for p in PUBLISHED]


def _normalise(raw: str) -> str:
    try:
        return str(Version(raw.removeprefix("v")))
    except InvalidVersion:
        sys.exit(f"error: {raw!r} is not a PEP 440 version (e.g. 2.0.0, 2.0.0a1, 2.1.0rc1)")


def _semver(v: Version) -> str:
    base = ".".join(str(p) for p in v.release)
    if v.pre is None:
        return base
    label = {"a": "alpha", "b": "beta", "rc": "rc"}[v.pre[0]]
    return f"{base}-{label}.{v.pre[1]}"


def current_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in _pyprojects():
        m = _VERSION_LINE.search(path.read_text(encoding="utf-8"))
        out[str(path.parent.relative_to(ROOT))] = m.group(1) if m else "?"
    return out


def bump(raw: str) -> None:
    version = _normalise(raw)
    published_names = set()
    for path in _pyprojects():
        m = re.search(r'^name = "([^"]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            published_names.add(m.group(1))

    def pin(match: re.Match[str]) -> str:
        name, extra = match.group(1), match.group(2) or ""
        if name not in published_names:
            return match.group(0)
        return f'"{name}{extra}=={version}"'

    for path in _pyprojects():
        text = path.read_text(encoding="utf-8")
        text = _VERSION_LINE.sub(f'version = "{version}"', text, count=1)
        # The list ends at a "]" that closes a line — extras like "[pii]" don't.
        text = _DEPS_BLOCK.sub(lambda m: _INTERNAL_DEP.sub(pin, m.group(0)), text, count=1)
        path.write_text(text, encoding="utf-8")

    pkg = json.loads(TS_PACKAGE.read_text(encoding="utf-8"))
    pkg["version"] = _semver(Version(version))
    TS_PACKAGE.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")

    print(f"Set {len(PUBLISHED)} Python packages to {version} and @aegis/sdk to {pkg['version']}.")
    print("Next: run `uv lock`, add a CHANGELOG section, commit, then tag v" + version)


def check(tag: str) -> None:
    expected = _normalise(tag)
    wrong = {pkg: v for pkg, v in current_versions().items() if v != expected}
    if wrong:
        lines = "\n".join(f"  {pkg}: {v}" for pkg, v in wrong.items())
        sys.exit(
            f"error: tag {tag} expects version {expected}, but these differ:\n{lines}\n"
            f"Run `uv run python scripts/release.py bump {expected}` and commit."
        )
    print(f"ok: all {len(PUBLISHED)} packages are at {expected}")


def notes(tag: str) -> None:
    """Print this version's CHANGELOG section, falling back to [Unreleased]."""
    version = _normalise(tag)
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for heading in (rf"## \[{re.escape(version)}\]", r"## \[Unreleased\]"):
        m = re.search(heading + r"[^\n]*\n(.*?)(?=\n## \[|\Z)", text, re.DOTALL)
        if m and m.group(1).strip():
            print(m.group(1).strip())
            return
    print(f"Release {version}. See CHANGELOG.md.")


def main(argv: list[str]) -> None:
    match argv:
        case ["bump", v]:
            bump(v)
        case ["check", tag]:
            check(tag)
        case ["notes", tag]:
            notes(tag)
        case ["packages"]:
            print("\n".join(PUBLISHED))
        case ["current"]:
            print(json.dumps(current_versions(), indent=2))
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
