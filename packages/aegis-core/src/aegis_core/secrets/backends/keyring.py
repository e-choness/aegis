"""KeyringSecretProvider — resolves secrets via the keyring library.

URI format: ``secret://keyring/<service>#<username>``

``<path>`` is the keyring service name; ``<key>`` is the username/account.

An in-memory stub backend is provided for testing environments where no
OS keychain is available (e.g. Docker containers).
"""

from __future__ import annotations

from pydantic import SecretStr

from aegis_core.errors import AegisSecretRefError
from aegis_core.secrets.ref import SecretRef


class InMemoryKeyring:
    """Minimal in-memory keyring backend for testing.

    Implements the interface that ``keyring`` expects from a backend
    (``get_password``, ``set_password``, ``delete_password``).
    """

    name = "in-memory (aegis test stub)"
    # Keyed as (service, username) → plaintext
    _store: dict[tuple[str, str], str]

    def __init__(self) -> None:
        self._store = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


class KeyringSecretProvider:
    """Resolves secrets using the ``keyring`` library.

    Pass an *override_backend* to replace the OS keychain with a test stub.
    If no override is supplied the provider imports ``keyring`` lazily, so
    the keyring dependency stays optional at import time.
    """

    scheme: str = "keyring"

    def __init__(self, override_backend: InMemoryKeyring | None = None) -> None:
        self._override = override_backend

    def resolve(self, ref: SecretRef) -> SecretStr:
        service = ref.path
        username = ref.key

        if self._override is not None:
            value = self._override.get_password(service, username)
        else:
            try:
                import keyring

                value = keyring.get_password(service, username)
            except Exception as exc:
                raise AegisSecretRefError(
                    f"keyring lookup failed for {ref.raw!r}: {exc}",
                    uri=ref.raw,
                ) from exc

        if value is None:
            raise AegisSecretRefError(
                f"No keyring entry for service={service!r} username={username!r} "
                f"(required by {ref.raw!r}).",
                uri=ref.raw,
                service=service,
                username=username,
            )
        return SecretStr(value)
