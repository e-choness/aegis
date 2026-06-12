"""Aegis hook system — pluggy-based hook specs and helpers."""

from __future__ import annotations

import pluggy

from aegis_core.hooks.specs import AegisSpec, hookimpl, hookspec

__all__ = ["AegisSpec", "get_plugin_manager", "hookimpl", "hookspec"]


def get_plugin_manager() -> pluggy.PluginManager:
    """Create and return a fresh PluginManager with all Aegis hook specs registered.

    Example::

        pm = get_plugin_manager()
        pm.register(MyHookPlugin())
        pm.hook.on_run_start(run_id="x", route="default", principal=None)
    """
    pm = pluggy.PluginManager("aegis")
    pm.add_hookspecs(AegisSpec)
    return pm
