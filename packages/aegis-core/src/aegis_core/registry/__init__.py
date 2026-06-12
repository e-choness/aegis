"""Aegis plugin registry — entry-point discovery."""

from __future__ import annotations

from aegis_core.registry.discovery import PLUGIN_GROUPS, PluginRegistry
from aegis_core.registry.models import PluginInfo

__all__ = ["PLUGIN_GROUPS", "PluginInfo", "PluginRegistry"]
