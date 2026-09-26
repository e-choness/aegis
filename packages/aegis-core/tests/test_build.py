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


# ── Plugin providers ──────────────────────────────────────────────────────────


class _PluginRegistry:
    """Registry stand-in exposing one aegis.providers entry point."""

    def __init__(self, name: str, target: object) -> None:
        from aegis_core.registry.models import PluginInfo

        self._name = name
        self._target = target
        self._info = PluginInfo(
            name=name, group="aegis.providers", value="x:y", dist_name="d", dist_version="1"
        )

    def load(self, name: str, group: str) -> object:
        from aegis_core.errors import AegisPluginNotFoundError

        if name != self._name or group != "aegis.providers":
            raise AegisPluginNotFoundError(name=name, group=group)
        return self._target

    def list_plugins(self, group: str | None = None) -> list:
        return [self._info]


class _ConfiguredProvider(FakeProvider):
    @classmethod
    def from_config(cls, name: str, cfg: ProviderConfig) -> _ConfiguredProvider:
        return cls(name=name, complete_response=getattr(cfg, "greeting", "hi"))


def test_build_provider_plugin_with_from_config() -> None:
    reg = _PluginRegistry("acme", _ConfiguredProvider)
    pcfg = ProviderConfig(type="acme", greeting="hello from acme")  # type: ignore[call-arg]
    provider = build_provider(pcfg, name="primary", registry=reg)  # type: ignore[arg-type]
    assert isinstance(provider, _ConfiguredProvider)
    assert provider.name == "primary"
    assert provider.complete_response == "hello from acme"


def test_build_provider_plugin_zero_arg() -> None:
    reg = _PluginRegistry("plain", FakeProvider)
    provider = build_provider(ProviderConfig(type="plain"), registry=reg)  # type: ignore[arg-type]
    assert isinstance(provider, FakeProvider)


def test_build_provider_plugin_must_be_a_model_provider() -> None:
    reg = _PluginRegistry("broken", object)
    with pytest.raises(AegisConfigValidationError, match="did not produce a ModelProvider"):
        build_provider(ProviderConfig(type="broken"), registry=reg)  # type: ignore[arg-type]


def test_build_provider_unknown_lists_installed_plugins() -> None:
    reg = _PluginRegistry("acme", FakeProvider)
    with pytest.raises(AegisConfigValidationError, match="installed provider plugins: acme"):
        build_provider(ProviderConfig(type="nope"), registry=reg)  # type: ignore[arg-type]


# ── Stages that cannot be wired yet fail closed ───────────────────────────────


@pytest.mark.parametrize("stage", ["tool_call", "tool_result"])
def test_build_executor_refuses_unwired_global_stage(stage: str) -> None:
    cfg = AegisConfig(
        providers={"fake": ProviderConfig(type="fake")},
        guardrails={"g": {"pack": "aegis.pii"}},  # type: ignore[dict-item]
        pipeline=PipelineConfig(**{stage: ["g"]}),
        routes={"default": RouteConfig(provider="fake")},
    )
    with pytest.raises(AegisConfigValidationError, match=rf"pipeline.{stage} is set"):
        build_executor(cfg, registry=MagicMock())


def test_build_executor_refuses_unwired_route_stage() -> None:
    cfg = AegisConfig(
        providers={"fake": ProviderConfig(type="fake")},
        guardrails={"g": {"pack": "aegis.pii"}},  # type: ignore[dict-item]
        routes={
            "default": RouteConfig(provider="fake", pipeline=PipelineConfig(tool_result=["g"]))
        },
    )
    with pytest.raises(AegisConfigValidationError, match=r"routes.default.pipeline.tool_result"):
        build_executor(cfg, registry=MagicMock())


# ── Built-in real providers ───────────────────────────────────────────────────


def test_build_openai_compatible_provider() -> None:
    from pydantic import SecretStr

    from aegis_core.config.models import ResidencyConfig
    from aegis_core.providers.openai_compatible import OpenAICompatibleProvider

    pcfg = ProviderConfig(
        type="openai_compatible",
        base_url="http://localhost:11434/v1",
        model="llama3.1",
        api_key=SecretStr("sk-test"),
        residency=ResidencyConfig(region="ca-central-1", jurisdiction="CA"),
    )
    provider = build_provider(pcfg, name="local")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "local"
    assert provider.info().residency.region == "ca-central-1"
    kwargs = provider._call_kwargs()
    assert kwargs["api_key"] == "sk-test"  # secret unwrapped only at call time
    assert kwargs["base_url"] == "http://localhost:11434/v1"
    assert kwargs["custom_llm_provider"] == "openai"  # arbitrary model names route correctly


def test_build_anthropic_provider() -> None:
    from pydantic import SecretStr

    from aegis_core.providers.litellm_provider import LiteLLMProvider

    pcfg = ProviderConfig(
        type="anthropic", model="anthropic/claude-sonnet-5", api_key=SecretStr("sk-ant")
    )
    provider = build_provider(pcfg, name="claude")

    assert isinstance(provider, LiteLLMProvider)
    assert provider.info().provider_type == "anthropic"
    assert provider._call_kwargs() == {"api_key": "sk-ant"}


@pytest.mark.parametrize(
    ("ptype", "fields", "missing"),
    [
        ("anthropic", {}, "model"),
        ("openai_compatible", {"model": "m"}, "base_url"),
        ("openai_compatible", {"base_url": "http://x/v1"}, "model"),
    ],
)
def test_build_provider_requires_fields(ptype: str, fields: dict, missing: str) -> None:
    with pytest.raises(AegisConfigValidationError, match=f"requires '{missing}'"):
        build_provider(ProviderConfig(type=ptype, **fields), name="p")


def test_build_executor_with_real_provider_types(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """End-to-end: YAML with secret refs → load → build must not crash."""
    monkeypatch.setenv("OPENAI_KEY", "sk-live")
    path = _write_yaml(
        tmp_path,
        """
        providers:
          local:
            type: openai_compatible
            base_url: http://localhost:11434/v1
            model: llama3.1
            api_key: secret://env/OPENAI_KEY#value
        routes:
          default:
            provider: local
        """,
    )
    executor = build_executor(load_config(path), registry=MagicMock())
    assert executor.routes() == ["default"]
