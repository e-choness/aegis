"""NoneAuthenticator — always returns an anonymous Principal (dev/--no-auth)."""

from __future__ import annotations

from starlette.requests import Request

from aegis_server.auth.protocol import Principal


class NoneAuthenticator:
    """No-op authenticator for development.  Every request is 'anonymous'."""

    async def authenticate(self, request: Request) -> Principal:
        return Principal(id="anonymous")
