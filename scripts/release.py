"""Release helper. The version of every published package is its git tag.

Packages don't declare a version: hatch-vcs derives it from git when they are
built (tag ``v2.0.0a3`` → ``2.0.0a3``; commits after it → ``2.0.0a4.devN``).
To release, push a tag — see docs/CONTRIBUTING.md. This script covers the
parts a tag can't:

    uv run python scripts/release.py changelog 2.0.0a3   # optional, before tagging:
                                                          #   Unreleased → [2.0.0a3] - <today>
    uv run python scripts/release.py pin v2.0.0a3        # CI: pin internal deps to ==2.0.0a3
    uv run python scripts/release.py verify v2.0.0a3 dist # CI: every built file is 2.0.0a3
    uv run python scripts/release.py notes v2.0.0a3      # this version's changelog section
    uv run python scripts/release.py packages            # paths of publishable packages

Internal dependencies are unpinned in the repository (the uv workspace links
them) and pinned exactly at release time, so ``pip install aegis-gateway==X``
can never mix components from different releases.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from packaging.utils import parse_sdist_filename, parse_wheel_filename
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
CHANGELOG = ROOT / "docs" / "changelog.md"

_NAME_LINE = re.compile(r'^name = "([^"]+)"$', re.MULTILINE)
_DEPS_BLOCK = re.compile(r"^dependencies = \[.*?\]$", re.MULTILINE | re.DOTALL)
# "aegis-gateway-core", "aegis-gateway-pack-pii[pii]", with or without a specifier
_INTERNAL_DEP = re.compile(r'"(aegis-gateway(?:-[a-z-]+)?)(\[[a-z-]+\])?(?:[=<>!~][^"]*)?"')


def _pyprojects() -> list[Path]:
    return [ROOT / p / "pyproject.toml" for p in PUBLISHED]


def _normalise(raw: str) -> str:
    try:
        return str(Version(raw.removeprefix("v")))
    except InvalidVersion:
        sys.exit(f"error: {raw!r} is not a PEP 440 version (e.g. v2.0.0, v2.0.0a1, v2.1.0rc1)")


def _published_names() -> set[str]:
    names = set()
    for path in _pyprojects():
        m = _NAME_LINE.search(path.read_text(encoding="utf-8"))
        if m:
            names.add(m.group(1))
    return names


def pin(tag: str) -> None:
    """Pin every internal dependency to exactly this release (CI, before building)."""
    version = _normalise(tag)
    names = _published_names()

    def exact(match: re.Match[str]) -> str:
        name, extra = match.group(1), match.group(2) or ""
        return f'"{name}{extra}=={version}"' if name in names else match.group(0)

    for path in _pyprojects():
        text = path.read_text(encoding="utf-8")
        # The list ends at a "]" that closes a line — extras like "[pii]" don't.
        text = _DEPS_BLOCK.sub(lambda m: _INTERNAL_DEP.sub(exact, m.group(0)), text, count=1)
        path.write_text(text, encoding="utf-8")
    print(f"Pinned internal dependencies to =={version} in {len(PUBLISHED)} packages.")


def verify(tag: str, dist_dir: str) -> None:
    """Fail unless every built file is exactly *tag*'s version, for every package."""
    version = Version(_normalise(tag))
    files = sorted(Path(dist_dir).glob("*.whl")) + sorted(Path(dist_dir).glob("*.tar.gz"))
    wrong, seen = [], set()
    for f in files:
        name, ver = (
            parse_wheel_filename(f.name)[:2] if f.suffix == ".whl" else parse_sdist_filename(f.name)
        )
        seen.add(str(name))
        if ver != version:
            wrong.append(f"{f.name} (is {ver})")
    missing = sorted(_published_names() - seen)
    if wrong or missing:
        sys.exit(f"error: built files don't match tag {tag}: wrong={wrong} missing={missing}")
    print(f"ok: {len(files)} files, all {len(seen)} packages at {version}")


def changelog(raw: str) -> None:
    """Turn ``## [Unreleased]`` into this version's section and start a fresh one."""
    version = _normalise(raw)
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"## [{version}]" in text:
        sys.exit(f"docs/changelog.md already has a [{version}] section")
    fresh = f"## [Unreleased]\n\n## [{version}] - {date.today().isoformat()}"
    CHANGELOG.write_text(text.replace("## [Unreleased]", fresh, 1), encoding="utf-8")
    print(f"docs/changelog.md: Unreleased → [{version}]. Commit it, then tag v{version}.")


def notes(tag: str) -> None:
    """Print this version's changelog section, falling back to [Unreleased]."""
    version = _normalise(tag)
    text = CHANGELOG.read_text(encoding="utf-8")
    for heading in (rf"## \[{re.escape(version)}\]", r"## \[Unreleased\]"):
        m = re.search(heading + r"[^\n]*\n(.*?)(?=\n## \[|\Z)", text, re.DOTALL)
        if m and m.group(1).strip():
            print(m.group(1).strip())
            return
    print(f"Release {version}. See https://e-choness.github.io/aegis/changelog")


def main(argv: list[str]) -> None:
    match argv:
        case ["pin", tag]:
            pin(tag)
        case ["verify", tag, dist_dir]:
            verify(tag, dist_dir)
        case ["changelog", version]:
            changelog(version)
        case ["notes", tag]:
            notes(tag)
        case ["packages"]:
            print("\n".join(PUBLISHED))
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
