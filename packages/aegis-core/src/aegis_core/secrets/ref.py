"""SecretRef — parses `secret://<backend>/<path>#<key>` URIs."""

from __future__ import annotations

import re

from aegis_core.errors import AegisSecretRefError

# Pattern: secret://<scheme>/<path>#<key>
# The <path> may contain slashes; <key> is the fragment after '#'.
_URI_RE = re.compile(
    r"^secret://(?P<scheme>[a-zA-Z][a-zA-Z0-9_-]*)/"
    r"(?P<path>[^#]+)"
    r"#(?P<key>[^#\s]+)$"
)


class SecretRef:
    """Parsed representation of a ``secret://`` URI."""

    __slots__ = ("key", "path", "raw", "scheme")

    def __init__(self, scheme: str, path: str, key: str, raw: str) -> None:
        self.scheme = scheme
        self.path = path
        self.key = key
        self.raw = raw

    @classmethod
    def parse(cls, uri: str) -> SecretRef:
        """Parse a ``secret://`` URI, raising ``AegisSecretRefError`` on bad syntax."""
        m = _URI_RE.match(uri)
        if not m:
            raise AegisSecretRefError(
                f"Cannot parse secret URI: {uri!r}",
                uri=uri,
            )
        return cls(
            scheme=m.group("scheme"),
            path=m.group("path"),
            key=m.group("key"),
            raw=uri,
        )

    @staticmethod
    def is_secret_uri(value: str) -> bool:
        """Return True if the string looks like a ``secret://`` URI."""
        return value.startswith("secret://")

    def __repr__(self) -> str:
        # Never expose resolved value — only the URI itself.
        return f"SecretRef(scheme={self.scheme!r}, path={self.path!r}, key={self.key!r})"
