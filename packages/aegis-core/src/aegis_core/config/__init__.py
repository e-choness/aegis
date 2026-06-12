"""Aegis config subsystem — typed pydantic models and YAML loader."""

from __future__ import annotations

from aegis_core.config.loader import load_config
from aegis_core.config.models import (
    AegisConfig,
    AuthConfig,
    GuardrailConfig,
    PipelineConfig,
    ProviderConfig,
    ResidencyConfig,
    RouteConfig,
)

__all__ = [
    "AegisConfig",
    "AuthConfig",
    "GuardrailConfig",
    "PipelineConfig",
    "ProviderConfig",
    "ResidencyConfig",
    "RouteConfig",
    "load_config",
]
