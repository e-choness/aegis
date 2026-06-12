"""SecretResolver — walks a config dict and resolves all secret:// URIs."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from aegis_core.errors import AegisSecretBackendError
from aegis_core.secrets.protocol import SecretProvider
from aegis_core.secrets.ref import SecretRef


class SecretResolver:
    """Holds a registry of :class:`SecretProvider` instances and resolves URIs.

    Usage::

        resolver = SecretResolver()
        resolver.register(EnvSecretProvider())
        resolver.register(KeyringSecretProvider(override_backend=stub))
        secret = resolver.resolve("secret://env/MY_VAR#value")
    """

    def __init__(self) -> None:
        self._providers: dict[str, SecretProvider] = {}

    def register(self, provider: SecretProvider) -> None:
        """Register a provider (keyed by its ``scheme``)."""
        self._providers[provider.scheme] = provider

    def resolve(self, uri: str) -> SecretStr:
        """Parse *uri* and dispatch to the matching backend.

        Raises:
            AegisSecretRefError: if the URI is malformed.
            AegisSecretBackendError: if no provider is registered for the scheme.
        """
        ref = SecretRef.parse(uri)
        provider = self._providers.get(ref.scheme)
        if provider is None:
            raise AegisSecretBackendError(
                f"No SecretProvider registered for scheme {ref.scheme!r} "
                f"(referenced by {uri!r}).",
                scheme=ref.scheme,
                uri=uri,
                available=list(self._providers),
            )
        return provider.resolve(ref)

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively walk *data* and replace ``secret://`` strings with resolved values.

        Resolved values are returned as ``SecretStr``; all other values are
        left unchanged.
        """
        return self._walk(data)  # type: ignore[return-value]

    def _walk(self, node: Any) -> Any:
        if isinstance(node, dict):
            return {k: self._walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [self._walk(item) for item in node]
        if isinstance(node, str) and SecretRef.is_secret_uri(node):
            return self.resolve(node)
        return node
