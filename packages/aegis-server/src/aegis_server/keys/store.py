"""KeyStore — SHA-256-hashed virtual key management (PROJECT_SPEC D17)."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from aegis_server.auth.protocol import Principal


class KeyStore:
    """In-memory key store with optional JSON-file persistence.

    Keys are generated here and never stored.  Only the SHA-256 digest of
    each key is persisted; the plaintext is returned exactly once from
    :meth:`create`.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        # {sha256_hex: {key_id, principal_id, team, labels, created_at}}
        self._data: dict[str, dict[str, object]] = {}
        if path is not None and path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create(
        self,
        principal_id: str,
        team: str = "",
        labels: dict[str, str] | None = None,
    ) -> str:
        """Generate a new key and store only its SHA-256 hash.

        Returns the plaintext key (``aeg-<64-hex-chars>``).
        The plaintext is **not** retained anywhere in the store.
        """
        raw = secrets.token_hex(32)           # 64 hex chars
        key = f"aeg-{raw}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        entry: dict[str, object] = {
            "key_id": f"key-{raw[:8]}",
            "principal_id": principal_id,
            "team": team,
            "labels": labels or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._data[key_hash] = entry
        if self._path is not None:
            self._save()
        return key

    def revoke(self, key_id: str) -> bool:
        """Remove the entry matching *key_id*.  Returns True if found."""
        for h, entry in list(self._data.items()):
            if entry["key_id"] == key_id:
                del self._data[h]
                if self._path is not None:
                    self._save()
                return True
        return False

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def lookup(self, key: str) -> Principal | None:
        """Validate a plaintext key and return its Principal, or None."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        entry = self._data.get(key_hash)
        if entry is None:
            return None
        return Principal(
            id=str(entry["principal_id"]),
            team=str(entry["team"]),
            labels=dict(entry["labels"]),  # type: ignore[arg-type]
        )

    def list(self) -> list[dict[str, object]]:
        """Return all entries.  Never contains hashes or plaintext keys."""
        return [dict(e) for e in self._data.values()]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def _load(self) -> None:
        assert self._path is not None
        self._data = json.loads(self._path.read_text())
