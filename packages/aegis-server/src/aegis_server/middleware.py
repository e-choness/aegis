"""AuthMiddleware — resolves Authenticator → Principal on every request."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class AuthMiddleware(BaseHTTPMiddleware):
    """Intercept every request, call the authenticator, attach Principal or 401."""

    def __init__(self, app: ASGIApp, *, authenticator: object) -> None:
        super().__init__(app)
        self._authenticator = authenticator

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        principal = await self._authenticator.authenticate(request)  # type: ignore[union-attr]
        if principal is None:
            return JSONResponse(
                {
                    "code": "AEG-AUTH-001",
                    "detail": (
                        "AEG-AUTH-001: unauthorized — no valid credential. "
                        "Provide a Bearer token with a valid aeg-... key."
                    ),
                },
                status_code=401,
            )
        request.state.principal = principal
        return await call_next(request)
