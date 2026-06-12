"""ApiKeyAuthenticator — validates Aegis virtual keys (Bearer aeg-…)."""

from __future__ import annotations

from starlette.requests import Request

from aegis_server.auth.protocol import Principal


class ApiKeyAuthenticator:
    """Validates ``Authorization: Bearer aeg-<key>`` against a KeyStore."""

    def __init__(self, store: object) -> None:
        # Accepts any object with a .lookup(key) -> Principal | None method
        # so we avoid a circular import with keys.store.
        self._store = store  # type: ignore[assignment]

    async def authenticate(self, request: Request) -> Principal | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer aeg-"):
            return None
        key = auth.removeprefix("Bearer ")
        return self._store.lookup(key)  # type: ignore[return-value]
