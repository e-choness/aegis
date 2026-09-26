"""Aegis v2 — core kernel."""

from __future__ import annotations

from importlib.metadata import version as _dist_version

#: Single source of truth is pyproject.toml (set by scripts/release.py bump).
__version__ = _dist_version("aegis-gateway-core")
