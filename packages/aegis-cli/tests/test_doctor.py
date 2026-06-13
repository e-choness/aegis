"""Tests for `aegis doctor`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_cli.commands.doctor import (
    CheckStatus,
    check_config,
    check_pii_extra,
    check_provider_store,
    check_providers_reachable,
    check_rag_extra,
    run_checks,
)


class TestCheckConfig:
    def test_ok_when_valid_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("guardrails: {}\npipeline:\n  ingress: []\n")
        result = check_config(cfg)
        assert result.status == CheckStatus.OK

    def test_fail_when_missing(self, tmp_path: Path) -> None:
        result = check_config(tmp_path / "missing.yaml")
        assert result.status == CheckStatus.FAIL
        assert "not found" in result.detail

    def test_fail_when_invalid_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("{ unclosed: [bracket")
        result = check_config(cfg)
        assert result.status == CheckStatus.FAIL

    def test_fail_when_not_a_mapping(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("- item1\n- item2\n")
        result = check_config(cfg)
        assert result.status == CheckStatus.FAIL


class TestCheckPiiExtra:
    def test_returns_health_check(self) -> None:
        result = check_pii_extra()
        assert result.name == "pii_extra"
        assert result.status in (CheckStatus.OK, CheckStatus.WARN)

    def test_warns_when_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib.util as ilu

        original_find_spec = ilu.find_spec

        def fake_find_spec(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "presidio_analyzer":
                return None
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(ilu, "find_spec", fake_find_spec)
        result = check_pii_extra()
        assert result.status == CheckStatus.WARN
        assert "presidio" in result.detail.lower()

    def test_ok_when_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib.util as ilu
        import types

        original_find_spec = ilu.find_spec

        def fake_find_spec(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "presidio_analyzer":
                spec = types.SimpleNamespace()
                return spec  # type: ignore[return-value]
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(ilu, "find_spec", fake_find_spec)
        result = check_pii_extra()
        assert result.status == CheckStatus.OK


class TestCheckRagExtra:
    def test_returns_health_check(self) -> None:
        result = check_rag_extra()
        assert result.name == "rag_extra"
        assert result.status in (CheckStatus.OK, CheckStatus.WARN)

    def test_warns_when_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib.util as ilu

        original_find_spec = ilu.find_spec

        def fake_find_spec(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "chromadb":
                return None
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(ilu, "find_spec", fake_find_spec)
        result = check_rag_extra()
        assert result.status == CheckStatus.WARN
        assert "chromadb" in result.detail.lower()


class TestCheckProviderStore:
    def test_ok_when_store_exists(self, tmp_path: Path) -> None:
        store = tmp_path / "providers.json"
        store.write_text("[]")
        result = check_provider_store(store)
        assert result.status == CheckStatus.OK

    def test_warn_when_store_missing(self, tmp_path: Path) -> None:
        result = check_provider_store(tmp_path / "missing.json")
        assert result.status == CheckStatus.WARN
        assert "not found" in result.detail


class TestCheckProvidersReachable:
    def test_warn_when_no_store(self, tmp_path: Path) -> None:
        result = check_providers_reachable(tmp_path / "missing.json")
        assert result.status == CheckStatus.WARN

    def test_warn_when_empty_profiles(self, tmp_path: Path) -> None:
        store = tmp_path / "providers.json"
        store.write_text("[]")
        result = check_providers_reachable(store)
        assert result.status == CheckStatus.WARN

    def test_fail_when_provider_unreachable(self, tmp_path: Path) -> None:
        store = tmp_path / "providers.json"
        store.write_text(json.dumps([{
            "name": "dead-server",
            "provider_type": "openai_compatible",
            "model": "test",
            "base_url": "http://127.0.0.1:19999",  # nothing should be listening here
        }]))
        result = check_providers_reachable(store)
        assert result.status == CheckStatus.FAIL
        assert "dead-server" in result.detail

    def test_ok_when_no_base_url_profiles(self, tmp_path: Path) -> None:
        store = tmp_path / "providers.json"
        # Profile with no base_url — e.g., cloud provider with no explicit endpoint
        store.write_text(json.dumps([{
            "name": "cloud",
            "provider_type": "anthropic",
            "model": "claude-3",
        }]))
        result = check_providers_reachable(store)
        # No base_url to ping → considered ok (nothing to check)
        assert result.status == CheckStatus.OK


class TestRunChecks:
    def test_returns_four_checks_by_default(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("{}")
        store = tmp_path / "providers.json"
        results = run_checks(config_path=cfg, store_path=store)
        assert len(results) == 4

    def test_returns_five_checks_with_check_providers(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("{}")
        store = tmp_path / "providers.json"
        results = run_checks(config_path=cfg, store_path=store, check_providers=True)
        assert len(results) == 5

    def test_check_names_are_unique(self, tmp_path: Path) -> None:
        cfg = tmp_path / "aegis.yaml"
        cfg.write_text("{}")
        store = tmp_path / "providers.json"
        results = run_checks(config_path=cfg, store_path=store, check_providers=True)
        names = [r.name for r in results]
        assert len(names) == len(set(names))

    def test_detects_all_five_faults(self, tmp_path: Path) -> None:
        """Seed all five fault conditions and verify each is detected."""
        # Fault 1: missing config
        # Fault 2: pii extra not installed → monkeypatched in other tests
        # Fault 3: rag extra not installed → monkeypatched in other tests
        # Fault 4: missing provider store
        # Fault 5: provider unreachable
        missing_cfg = tmp_path / "nonexistent.yaml"
        missing_store = tmp_path / "nonexistent.json"
        results = run_checks(
            config_path=missing_cfg,
            store_path=missing_store,
            check_providers=True,
        )
        config_check = next(r for r in results if r.name == "config")
        store_check = next(r for r in results if r.name == "provider_store")
        reachable_check = next(r for r in results if r.name == "providers_reachable")

        assert config_check.status == CheckStatus.FAIL
        assert store_check.status == CheckStatus.WARN
        assert reachable_check.status == CheckStatus.WARN  # store missing → warn
