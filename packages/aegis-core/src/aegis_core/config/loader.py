"""Config loader — reads aegis.yaml and applies env overrides.

Loading sequence:
1. Parse the YAML file into a raw dict.
2. Walk the raw dict with ``SecretResolver`` to replace ``secret://`` URIs.
3. Apply pydantic-settings env overrides (``AEGIS__<SECTION>__<KEY>=...``).
4. Validate with ``AegisConfig``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aegis_core.config.models import AegisConfig
from aegis_core.errors import AegisConfigNotFoundError, AegisConfigValidationError
from aegis_core.secrets.backends.env import EnvSecretProvider
from aegis_core.secrets.resolver import SecretResolver

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required to load aegis.yaml. "
        "Install it with: uv add pyyaml"
    ) from exc


def _build_default_resolver() -> SecretResolver:
    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    return resolver


def load_config(
    path: str | Path,
    *,
    resolver: SecretResolver | None = None,
    env_prefix: str = "AEGIS",
) -> AegisConfig:
    """Load and validate an ``aegis.yaml`` file.

    Args:
        path: Path to ``aegis.yaml``.
        resolver: Optional :class:`~aegis_core.secrets.SecretResolver`.  If not
            supplied a default one (env-only) is constructed.
        env_prefix: Prefix for environment-variable overrides.  Variables of the
            form ``AEGIS__ROUTES__DEFAULT__MODEL`` override nested config keys
            (double-underscore as separator).

    Returns:
        Validated :class:`~aegis_core.config.models.AegisConfig` instance.

    Raises:
        AegisConfigNotFoundError: if *path* does not exist.
        AegisConfigValidationError: if the YAML is structurally valid but fails
            Pydantic validation.
    """
    p = Path(path)
    if not p.exists():
        raise AegisConfigNotFoundError(
            f"Configuration file not found: {p}",
            path=str(p),
        )

    with p.open("rb") as fh:
        raw: Any = yaml.safe_load(fh)

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise AegisConfigValidationError(
            "aegis.yaml must be a YAML mapping at the top level.",
            path=str(p),
        )

    # Resolve secret:// URIs
    if resolver is None:
        resolver = _build_default_resolver()
    raw = resolver.resolve_dict(raw)

    # Apply env overrides (double-underscore path separator)
    raw = _apply_env_overrides(raw, prefix=env_prefix)

    # Validate
    from pydantic import ValidationError

    try:
        return AegisConfig.model_validate(raw)
    except ValidationError as exc:
        raise AegisConfigValidationError(
            f"Configuration validation failed:\n{exc}",
            path=str(p),
        ) from exc


def _apply_env_overrides(data: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Overlay ``<PREFIX>__KEY1__KEY2=value`` env vars onto *data*.

    Only variables that start with ``<prefix>__`` (case-insensitive) are
    considered.  Double-underscore is the nesting separator.
    """
    prefix_upper = prefix.upper() + "__"
    for key, value in os.environ.items():
        if not key.upper().startswith(prefix_upper):
            continue
        remainder = key[len(prefix_upper):]
        parts = [p.lower() for p in remainder.split("__")]
        _set_nested(data, parts, value)
    return data


def _set_nested(data: dict[str, Any], keys: list[str], value: str) -> None:
    """Set *data*[keys[0]][keys[1]]… = *value*, creating dicts as needed."""
    node = data
    for k in keys[:-1]:
        if k not in node or not isinstance(node[k], dict):
            node[k] = {}
        node = node[k]
    node[keys[-1]] = value
