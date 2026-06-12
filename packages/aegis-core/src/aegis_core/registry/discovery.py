"""Plugin registry — importlib.metadata entry-point discovery."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from aegis_core.errors import AegisPluginDuplicateError, AegisPluginNotFoundError
from aegis_core.registry.models import PluginInfo

#: All known entry-point groups (PROJECT_SPEC §10).
PLUGIN_GROUPS: tuple[str, ...] = (
    "aegis.providers",
    "aegis.guardrails",
    "aegis.secrets",
    "aegis.authenticators",
    "aegis.nodes",
    "aegis.vectorstores",
    "aegis.exporters",
)


class PluginRegistry:
    """Discovers and tracks Aegis plugins from package entry points.

    Usage::

        registry = PluginRegistry()
        registry.discover()
        plugins = registry.list_plugins()
    """

    def __init__(self) -> None:
        # group → {name → PluginInfo}
        self._plugins: dict[str, dict[str, PluginInfo]] = {g: {} for g in PLUGIN_GROUPS}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, groups: tuple[str, ...] | None = None) -> None:
        """Scan installed packages for entry points in all known groups.

        Args:
            groups: Subset of groups to scan. Defaults to all known groups.

        Raises:
            AegisPluginDuplicateError: If two packages declare the same name
                in the same group (AEG-CFG-021).
        """
        target_groups = groups if groups is not None else PLUGIN_GROUPS
        for group in target_groups:
            eps = importlib.metadata.entry_points(group=group)
            for ep in eps:
                if ep.name in self._plugins.get(group, {}):
                    existing = self._plugins[group][ep.name]
                    raise AegisPluginDuplicateError(
                        f"Plugin '{ep.name}' in group '{group}' is declared by "
                        f"both '{existing.dist_name}' and '{ep.dist.name if ep.dist else '?'}'.",
                        name=ep.name,
                        group=group,
                    )
                dist_name = ep.dist.name if ep.dist else ""
                dist_version = ep.dist.version if ep.dist else ""
                info = PluginInfo(
                    name=ep.name,
                    group=group,
                    value=ep.value,
                    dist_name=dist_name,
                    dist_version=dist_version,
                )
                if group not in self._plugins:
                    self._plugins[group] = {}
                self._plugins[group][ep.name] = info

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_plugins(self, group: str | None = None) -> list[PluginInfo]:
        """Return all discovered plugins, optionally filtered by group."""
        if group is not None:
            return list(self._plugins.get(group, {}).values())
        result: list[PluginInfo] = []
        for plugins in self._plugins.values():
            result.extend(plugins.values())
        return result

    def get(self, name: str, group: str) -> PluginInfo:
        """Return a specific plugin by name and group.

        Raises:
            AegisPluginNotFoundError: If not found (AEG-CFG-022).
        """
        info = self._plugins.get(group, {}).get(name)
        if info is None:
            raise AegisPluginNotFoundError(
                f"No plugin named '{name}' in group '{group}'.",
                name=name,
                group=group,
            )
        return info

    def load(self, name: str, group: str) -> Any:
        """Load and return the object referenced by the entry point.

        Raises:
            AegisPluginNotFoundError: If not found (AEG-CFG-022).
        """
        info = self.get(name, group)
        ep = importlib.metadata.entry_points(group=group)
        for e in ep:
            if e.name == name:
                obj = e.load()
                info.loaded = True
                return obj
        raise AegisPluginNotFoundError(  # pragma: no cover
            f"Entry point for '{name}' in '{group}' disappeared after discovery.",
            name=name,
            group=group,
        )
