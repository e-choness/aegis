"""Aegis v2 — server package."""

from importlib.metadata import version as _dist_version

#: Single source of truth is pyproject.toml (set by scripts/release.py bump).
__version__ = _dist_version("aegis-gateway-server")
