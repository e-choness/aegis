"""Tests for aegis_core.registry — entry-point discovery and plugin registry."""

from __future__ import annotations

import importlib.metadata
from unittest.mock import MagicMock, patch

import pytest

from aegis_core.errors import AegisPluginDuplicateError, AegisPluginNotFoundError
from aegis_core.registry import PLUGIN_GROUPS, PluginInfo, PluginRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ep(name: str, group: str, value: str, dist_name: str = "test-dist") -> MagicMock:
    """Build a mock entry point matching importlib.metadata.EntryPoint."""
    ep = MagicMock(spec=importlib.metadata.EntryPoint)
    ep.name = name
    ep.group = group
    ep.value = value
    ep.dist = MagicMock()
    ep.dist.name = dist_name
    ep.dist.version = "1.0.0"
    return ep


# ---------------------------------------------------------------------------
# PLUGIN_GROUPS constant
# ---------------------------------------------------------------------------


def test_plugin_groups_contains_all_spec_groups() -> None:
    expected = {
        "aegis.providers",
        "aegis.guardrails",
        "aegis.secrets",
        "aegis.authenticators",
        "aegis.nodes",
        "aegis.vectorstores",
        "aegis.exporters",
    }
    assert set(PLUGIN_GROUPS) == expected


# ---------------------------------------------------------------------------
# Discovery: fixture plugin (installed editable in the test session)
# ---------------------------------------------------------------------------


def test_registry_discovers_fixture_provider() -> None:
    """The installed aegis-fixture-plugin must appear in aegis.providers."""
    registry = PluginRegistry()
    registry.discover(groups=("aegis.providers",))
    plugins = registry.list_plugins(group="aegis.providers")
    names = [p.name for p in plugins]
    assert "fixture-provider" in names, (
        f"Expected 'fixture-provider' in aegis.providers, got: {names}"
    )


def test_registry_discovers_fixture_guardrail() -> None:
    registry = PluginRegistry()
    registry.discover(groups=("aegis.guardrails",))
    plugins = registry.list_plugins(group="aegis.guardrails")
    names = [p.name for p in plugins]
    assert "fixture-guardrail" in names


def test_plugin_info_has_correct_fields() -> None:
    registry = PluginRegistry()
    registry.discover(groups=("aegis.providers",))
    info = registry.get("fixture-provider", "aegis.providers")
    assert info.name == "fixture-provider"
    assert info.group == "aegis.providers"
    assert "aegis_fixture_plugin" in info.value
    assert info.dist_name  # non-empty


def test_list_plugins_no_filter_includes_all_groups() -> None:
    """list_plugins() with no group arg returns plugins from all groups."""
    registry = PluginRegistry()
    registry.discover()
    all_plugins = registry.list_plugins()
    provider_plugins = registry.list_plugins(group="aegis.providers")
    guardrail_plugins = registry.list_plugins(group="aegis.guardrails")
    # All-group list must be at least as large as individual groups combined.
    assert len(all_plugins) >= len(provider_plugins) + len(guardrail_plugins)


# ---------------------------------------------------------------------------
# Discovery: duplicate name raises AEG-CFG-021
# ---------------------------------------------------------------------------


def test_duplicate_plugin_name_raises() -> None:
    """Two entry points with the same name in the same group → AEG-CFG-021."""
    ep_a = _make_ep("clash", "aegis.providers", "pkg_a:ProviderA", dist_name="pkg-a")
    ep_b = _make_ep("clash", "aegis.providers", "pkg_b:ProviderB", dist_name="pkg-b")

    with patch("importlib.metadata.entry_points", return_value=[ep_a, ep_b]):
        registry = PluginRegistry()
        with pytest.raises(AegisPluginDuplicateError) as exc_info:
            registry.discover(groups=("aegis.providers",))

    assert "AEG-CFG-021" in str(exc_info.value)
    assert "clash" in str(exc_info.value)


def test_duplicate_error_mentions_fix() -> None:
    ep_a = _make_ep("clash", "aegis.guardrails", "pkg_a:G", dist_name="pkg-a")
    ep_b = _make_ep("clash", "aegis.guardrails", "pkg_b:G", dist_name="pkg-b")

    with patch("importlib.metadata.entry_points", return_value=[ep_a, ep_b]):
        registry = PluginRegistry()
        with pytest.raises(AegisPluginDuplicateError) as exc_info:
            registry.discover(groups=("aegis.guardrails",))

    assert "Fix:" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get() and load()
# ---------------------------------------------------------------------------


def test_get_unknown_plugin_raises_not_found() -> None:
    registry = PluginRegistry()
    registry.discover()
    with pytest.raises(AegisPluginNotFoundError) as exc_info:
        registry.get("no-such-plugin", "aegis.providers")
    assert "AEG-CFG-022" in str(exc_info.value)
    assert "no-such-plugin" in str(exc_info.value)
    assert "Fix:" in str(exc_info.value)


def test_get_wrong_group_raises_not_found() -> None:
    """fixture-provider is in aegis.providers, not aegis.guardrails."""
    registry = PluginRegistry()
    registry.discover()
    with pytest.raises(AegisPluginNotFoundError):
        registry.get("fixture-provider", "aegis.guardrails")


def test_load_fixture_provider_returns_class() -> None:
    registry = PluginRegistry()
    registry.discover(groups=("aegis.providers",))
    obj = registry.load("fixture-provider", "aegis.providers")
    # The fixture entry point points to FixtureProvider class
    assert obj.__name__ == "FixtureProvider"


def test_load_sets_loaded_flag() -> None:
    registry = PluginRegistry()
    registry.discover(groups=("aegis.providers",))
    info_before = registry.get("fixture-provider", "aegis.providers")
    assert info_before.loaded is False
    registry.load("fixture-provider", "aegis.providers")
    info_after = registry.get("fixture-provider", "aegis.providers")
    assert info_after.loaded is True


# ---------------------------------------------------------------------------
# PluginInfo model
# ---------------------------------------------------------------------------


def test_plugin_info_module_path() -> None:
    info = PluginInfo(name="p", group="aegis.providers", value="my.module:MyClass")
    assert info.module_path == "my.module"
    assert info.attr == "MyClass"


def test_plugin_info_value_without_colon() -> None:
    info = PluginInfo(name="p", group="aegis.providers", value="my.module")
    assert info.module_path == "my.module"
    assert info.attr is None


# ---------------------------------------------------------------------------
# Mocked discovery: no entry points in empty group
# ---------------------------------------------------------------------------


def test_empty_group_returns_empty_list() -> None:
    with patch("importlib.metadata.entry_points", return_value=[]):
        registry = PluginRegistry()
        registry.discover(groups=("aegis.exporters",))
    assert registry.list_plugins(group="aegis.exporters") == []
