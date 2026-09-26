"""Aegis v2 Python SDK — sync and async clients."""

from __future__ import annotations

from importlib.metadata import version as _dist_version

from aegis_sdk.client import AegisClient, AsyncAegisClient
from aegis_sdk.models import ResumeResponse, RunCreateResponse, RunStatusResponse

__all__ = [
    "AegisClient",
    "AsyncAegisClient",
    "ResumeResponse",
    "RunCreateResponse",
    "RunStatusResponse",
]

__version__ = _dist_version("aegis-gateway-sdk")
