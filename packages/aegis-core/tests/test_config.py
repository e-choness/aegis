"""Tests for aegis_core.config — models, loader, and env layering."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest
from pydantic import SecretStr

from aegis_core.config import AegisConfig, load_config
from aegis_core.config.models import (
    AuthConfig,
    PipelineConfig,
    ProviderConfig,
    RouteConfig,
)
from aegis_core.errors import (
    AegisConfigNotFoundError,
    AegisConfigValidationError,
)
from aegis_core.secrets.backends.env import EnvSecretProvider
from aegis_core.secrets.resolver import SecretResolver

# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "aegis.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def _minimal_resolver() -> SecretResolver:
    r = SecretResolver()
    r.register(EnvSecretProvider())
    return r


# ── Round-trip tests ──────────────────────────────────────────────────────────


def test_round_trip_minimal(tmp_path: Path) -> None:
    """A minimal config with one provider and one route loads cleanly."""
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          local:
            type: openai_compatible
            base_url: http://localhost:11434/v1
        routes:
          default:
            provider: local
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    assert isinstance(cfg, AegisConfig)
    assert "local" in cfg.providers
    assert cfg.providers["local"].type == "openai_compatible"
    assert cfg.routes["default"].provider == "local"


def test_round_trip_full(tmp_path: Path) -> None:
    """The example aegis.yaml (with env secrets pre-set) round-trips."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key-value"
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          anthropic_main:
            type: anthropic
            api_key: secret://env/ANTHROPIC_API_KEY#value
        guardrails:
          pii:
            pack: aegis.pii
            mode: mask
        pipeline:
          ingress: [pii]
          egress: [pii]
        routes:
          default:
            provider: anthropic_main
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    assert cfg.providers["anthropic_main"].api_key == SecretStr("test-key-value")
    assert cfg.pipeline.ingress == ["pii"]


def test_empty_yaml_loads(tmp_path: Path) -> None:
    """An empty YAML file produces a default-valued AegisConfig."""
    p = tmp_path / "aegis.yaml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg.providers == {}
    assert cfg.routes == {}


# ── Env override layering ──────────────────────────────────────────────────────


def test_env_override_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AEGIS__ROUTES__DEFAULT__MODEL overrides the model field."""
    monkeypatch.setenv("AEGIS__ROUTES__DEFAULT__MODEL", "gpt-4o-mini")
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          openai:
            type: openai_compatible
        routes:
          default:
            provider: openai
            model: original-model
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    assert cfg.routes["default"].model == "gpt-4o-mini"


def test_env_override_creates_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An env var can set a deeply nested key even if intermediate dicts are missing."""
    monkeypatch.setenv("AEGIS__AUTH__TYPE", "api_key")
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          local:
            type: openai_compatible
        routes:
          default:
            provider: local
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    assert cfg.auth.type == "api_key"


# ── Validation errors (AEG-CFG-*) ────────────────────────────────────────────


def test_unknown_provider_in_route(tmp_path: Path) -> None:
    """A route referencing an undeclared provider raises AEG-CFG-003."""
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers: {}
        routes:
          default:
            provider: nonexistent
        """,
    )
    with pytest.raises(AegisConfigValidationError) as exc_info:
        load_config(cfg_path)
    assert "AEG-CFG-003" in str(exc_info.value)
    assert "nonexistent" in str(exc_info.value)


def test_unknown_guardrail_in_pipeline(tmp_path: Path) -> None:
    """A pipeline referencing an undeclared guardrail raises AEG-CFG-003."""
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          local:
            type: openai_compatible
        routes:
          default:
            provider: local
        pipeline:
          ingress: [ghost_guard]
        """,
    )
    with pytest.raises(AegisConfigValidationError) as exc_info:
        load_config(cfg_path)
    assert "AEG-CFG-003" in str(exc_info.value)
    assert "ghost_guard" in str(exc_info.value)


def test_config_not_found() -> None:
    """Loading a non-existent file raises AEG-CFG-002."""
    with pytest.raises(AegisConfigNotFoundError) as exc_info:
        load_config("/nonexistent/path/aegis.yaml")
    assert "AEG-CFG-002" in str(exc_info.value)


def test_config_not_found_has_fix_hint() -> None:
    """AEG-CFG-002 error includes a fix hint."""
    with pytest.raises(AegisConfigNotFoundError) as exc_info:
        load_config("/nonexistent/path/aegis.yaml")
    msg = str(exc_info.value)
    assert "Fix:" in msg


# ── SecretStr redaction ────────────────────────────────────────────────────────


def test_secret_str_not_in_repr(tmp_path: Path) -> None:
    """The resolved API key must never appear in the model repr."""
    os.environ["_AEGIS_TEST_KEY"] = "super-secret-value"
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          p1:
            type: openai_compatible
            api_key: secret://env/_AEGIS_TEST_KEY#value
        routes:
          default:
            provider: p1
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    r = repr(cfg)
    assert "super-secret-value" not in r


def test_secret_str_not_in_safe_dict(tmp_path: Path) -> None:
    """safe_dict() must replace SecretStr values with **REDACTED**."""
    os.environ["_AEGIS_TEST_KEY2"] = "another-secret"
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          p1:
            type: openai_compatible
            api_key: secret://env/_AEGIS_TEST_KEY2#value
        routes:
          default:
            provider: p1
        """,
    )
    cfg = load_config(cfg_path, resolver=_minimal_resolver())
    safe = cfg.safe_dict()
    import json

    serialised = json.dumps(safe)
    assert "another-secret" not in serialised
    assert "**REDACTED**" in serialised


def test_secret_str_not_in_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """SecretStr values must not appear in any log output during loading."""
    import logging

    os.environ["_AEGIS_TEST_KEY3"] = "log-leak-secret"
    cfg_path = _write_yaml(
        tmp_path,
        """\
        providers:
          p1:
            type: openai_compatible
            api_key: secret://env/_AEGIS_TEST_KEY3#value
        routes:
          default:
            provider: p1
        """,
    )
    with caplog.at_level(logging.DEBUG):
        load_config(cfg_path, resolver=_minimal_resolver())
    assert "log-leak-secret" not in caplog.text


# ── AegisConfig model tests ───────────────────────────────────────────────────


def test_aegis_config_defaults() -> None:
    """AegisConfig built from an empty dict has sensible defaults."""
    cfg = AegisConfig.model_validate({})
    assert cfg.providers == {}
    assert cfg.guardrails == {}
    assert cfg.pipeline == PipelineConfig()
    assert cfg.routes == {}
    assert cfg.auth == AuthConfig()


def test_provider_config_extra_fields_allowed() -> None:
    """ProviderConfig accepts extra fields (provider-specific options)."""
    p = ProviderConfig.model_validate({"type": "openai_compatible", "timeout": 30})
    assert p.type == "openai_compatible"


def test_route_config_extra_fields_allowed() -> None:
    """RouteConfig accepts extra fields."""
    r = RouteConfig.model_validate({"provider": "local", "temperature": 0.7})
    assert r.provider == "local"
