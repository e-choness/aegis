"""Principal model and Authenticator contract (PROJECT_SPEC §4, D17)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from starlette.requests import Request


@dataclass
class Principal:
    """Resolved identity for a request."""

    id: str
    team: str = ""
    labels: dict[str, str] = field(default_factory=dict)


class Authenticator(Protocol):
    """Resolve an inbound request to a Principal, or None to reject."""

    async def authenticate(self, request: Request) -> Principal | None: ...
