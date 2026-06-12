"""Pydantic v2 models for aegis.yaml configuration.

All credentials are stored as ``pydantic.SecretStr`` so that they are
automatically redacted in ``repr``, logs, and serialized output.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class _StrictModel(BaseModel):
    """Shared base — forbids extra fields so typos surface as errors."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ── Residency ────────────────────────────────────────────────────────────────


class ResidencyConfig(_StrictModel):
    region: str
    jurisdiction: str | None = None
    source_url: str | None = None


# ── Providers ────────────────────────────────────────────────────────────────


class ProviderConfig(_StrictModel):
    """A single LLM provider profile."""

    type: str  # e.g. "anthropic", "openai_compatible"
    api_key: SecretStr | None = None
    base_url: str | None = None
    model: str | None = None
    residency: ResidencyConfig | None = None
    # Allow extra provider-specific fields without failing validation
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def _coerce_secret(cls, v: Any) -> Any:
        # secret:// URIs are resolved later by SecretResolver; pass through.
        return v


# ── Guardrails ────────────────────────────────────────────────────────────────


class GuardrailConfig(_StrictModel):
    pack: str
    mode: str | None = None
    scanners: list[str] | None = None
    threshold: float | None = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── Pipeline ──────────────────────────────────────────────────────────────────


class PipelineConfig(_StrictModel):
    ingress: list[str] = Field(default_factory=list)
    tool_call: list[str] = Field(default_factory=list)
    tool_result: list[str] = Field(default_factory=list)
    egress: list[str] = Field(default_factory=list)


# ── Routes ────────────────────────────────────────────────────────────────────


class RouteConfig(_StrictModel):
    provider: str
    model: str | None = None
    pipeline: PipelineConfig | None = None
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── Auth ──────────────────────────────────────────────────────────────────────


class AuthConfig(_StrictModel):
    type: Literal["none", "api_key"] = "none"
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ── Top-level AegisConfig ─────────────────────────────────────────────────────


class AegisConfig(_StrictModel):
    """Root configuration object for an Aegis gateway instance."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    guardrails: dict[str, GuardrailConfig] = Field(default_factory=dict)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    routes: dict[str, RouteConfig] = Field(default_factory=dict)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @model_validator(mode="after")
    def _validate_route_providers(self) -> AegisConfig:
        """All routes must reference a declared provider."""
        from aegis_core.errors import AegisConfigValidationError

        for route_name, route in self.routes.items():
            if route.provider not in self.providers:
                raise AegisConfigValidationError(
                    f"Route {route_name!r} references unknown provider "
                    f"{route.provider!r}. "
                    f"Declared providers: {list(self.providers)}",
                    route=route_name,
                    provider=route.provider,
                )
        return self

    @model_validator(mode="after")
    def _validate_pipeline_guardrails(self) -> AegisConfig:
        """Pipeline node references must be declared guardrails or qualified names."""
        from aegis_core.errors import AegisConfigValidationError

        all_refs: list[str] = (
            self.pipeline.ingress
            + self.pipeline.tool_call
            + self.pipeline.tool_result
            + self.pipeline.egress
        )
        for ref in all_refs:
            # Strip any ".unmask" or similar suffixes for lookup
            base = ref.split(".")[0]
            if base not in self.guardrails:
                raise AegisConfigValidationError(
                    f"Pipeline references unknown guardrail {ref!r}. "
                    f"Declared guardrails: {list(self.guardrails)}",
                    guardrail_ref=ref,
                )
        return self

    def safe_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict with all secrets redacted.

        ``SecretStr`` fields are replaced with ``"**REDACTED**"`` so the
        output is safe to display in CLI output or logs.
        """
        raw = self.model_dump(mode="python")
        return _redact(raw)


# ── Helpers ───────────────────────────────────────────────────────────────────

_REDACTED = "**REDACTED**"


def _redact(node: Any) -> Any:
    if isinstance(node, SecretStr):
        return _REDACTED
    if isinstance(node, dict):
        return {k: _redact(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_redact(item) for item in node]
    return node


