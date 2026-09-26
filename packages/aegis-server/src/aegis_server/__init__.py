"""Aegis v2 — server package."""

from importlib.metadata import version as _dist_version

#: Derived from the git tag at build time (hatch-vcs), e.g. 2.0.0a3 or 2.0.0a4.dev2.
__version__ = _dist_version("aegis-gateway-server")
