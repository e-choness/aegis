"""Aegis secrets subsystem — SecretRef resolution and SecretProvider protocol."""

from __future__ import annotations

from aegis_core.secrets.backends.env import EnvSecretProvider
from aegis_core.secrets.backends.keyring import KeyringSecretProvider
from aegis_core.secrets.protocol import SecretProvider
from aegis_core.secrets.ref import SecretRef
from aegis_core.secrets.resolver import SecretResolver

__all__ = [
    "EnvSecretProvider",
    "KeyringSecretProvider",
    "SecretProvider",
    "SecretRef",
    "SecretResolver",
]
