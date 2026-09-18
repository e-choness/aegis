"""Tests for aegis_core.config.build — build_executor, build_provider, config_digest."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aegis_core.config.build import build_executor, build_provider, config_digest
from aegis_core.config.loader import load_config
from aegis_core.config.models import AegisConfig, PipelineConfig, ProviderConfig, RouteConfig
from aegis_core.errors import AegisConfigValidationError
from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "aegis.yaml"
    p.write_text(textwrap.dedent(content))
    return p


def _fake_cfg(
    *,
    provider_name: str = "fake",
    route_name: str = "default",
    guardrails: dict | None = None,
    pipeline_ingress: list[str] | None = None,
) -> AegisConfig:
    """Build a minimal AegisConfig with a fake provider in-memory."""
    return AegisConfig(
        providers={provider_name: ProviderConfig(type="fake")},
        routes={
            route_name: RouteConfig(
                provider=provider_name,
                pipeline=PipelineConfig(ingress=pipeline_ingress or []),
            )
        },
        guardrails=guardrails or {},
    )


# ── build_provider ─────────────────────────────────────────────────────────────


def test_build_provider_fake() -> None:
    pcfg = ProviderConfig(type="fake", complete_response="hi")
    provider = build_provider(pcfg)
    assert isinstance(provider, FakeProvider)


def test_build_provider_unknown_raises() -> None:
    pcfg = ProviderConfig(type="unknown_xyz")
    with pytest.raises(AegisConfigValidationError, match="Unknown provider type"):
        build_provider(pcfg)


# ── build_executor ─────────────────────────────────────────────────────────────


def test_build_executor_no_guardrails() -> None:
    cfg = _fake_cfg()
    ex = build_executor(cfg)
    assert isinstance(ex, PipelineExecutor)


def test_build_executor_registers_route() -> None:
    cfg = _fake_cfg(route_name="default")
    ex = build_executor(cfg)
    # Executor should have the route registered (provider accessible via state).
    # We verify by checking the internal _pipelines dict (implementation detail OK in unit tests).
    assert "default" in ex._pipelines


def test_build_executor_unknown_pack_raises() -> None:
    """A guardrail referencing a non-installed pack raises AegisPluginNotFoundError."""
    from aegis_core.errors import AegisPluginNotFoundError

    cfg = AegisConfig(
        providers={"fake": ProviderConfig(type="fake")},
        routes={"default": RouteConfig(provider="fake")},
        guardrails={"bad": {"pack": "aegis.nonexistent_pack_xyz"}},
    )
    with pytest.raises(AegisPluginNotFoundError):
        build_executor(cfg)


def test_build_executor_bad_factory_shape_raises() -> None:
    """A pack factory that returns a non-dict triggers AegisConfigValidationError."""
    from aegis_core.registry.discovery import PluginRegistry

    bad_factory = MagicMock(return_value="not-a-dict")
    registry = MagicMock(spec=PluginRegistry)
    registry.load.return_value = bad_factory

    cfg = AegisConfig(
        providers={"fake": ProviderConfig(type="fake")},
        routes={"default": RouteConfig(provider="fake")},
        guardrails={"g": {"pack": "aegis.something"}},
    )
    with pytest.raises(AegisConfigValidationError, match="must return a dict"):
        build_executor(cfg, registry=registry)


# ── config_digest ──────────────────────────────────────────────────────────────


def test_config_digest_format() -> None:
    cfg = _fake_cfg()
    digest = config_digest(cfg)
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64  # 256-bit hex


def test_config_digest_stable() -> None:
    cfg = _fake_cfg()
    assert config_digest(cfg) == config_digest(cfg)


def test_config_digest_differs_on_change() -> None:
    cfg_a = _fake_cfg(route_name="route_a")
    cfg_b = _fake_cfg(route_name="route_b")
    assert config_digest(cfg_a) != config_digest(cfg_b)


# ── Integration: load_config + build_executor ─────────────────────────────────


def test_load_and_build_fake_provider(tmp_path: Path) -> None:
    """Full round-trip: YAML → load_config → build_executor."""
    p = _write_yaml(
        tmp_path,
        """\
        providers:
          fake:
            type: fake
            complete_response: hi
        routes:
          default:
            provider: fake
        """,
    )
    cfg = load_config(p)
    ex = build_executor(cfg)
    assert isinstance(ex, PipelineExecutor)
    assert "default" in ex._pipelines
