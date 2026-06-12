"""SecretProvider Protocol — contract for secret backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import SecretStr

from aegis_core.secrets.ref import SecretRef


@runtime_checkable
class SecretProvider(Protocol):
    """Resolves a ``SecretRef`` to a ``SecretStr``.

    Implementations must set ``scheme`` to the URI scheme they handle
    (e.g. ``"env"``, ``"keyring"``).
    """

    scheme: str

    def resolve(self, ref: SecretRef) -> SecretStr:
        """Resolve *ref* and return the secret value.

        Raises ``AegisSecretRefError`` if the secret cannot be found.
        """
        ...
