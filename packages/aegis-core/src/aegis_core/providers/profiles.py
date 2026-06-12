"""Provider profile store — persists named provider profiles to a JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aegis_core.errors import AegisProviderNotFoundError


@dataclass
class ProviderProfile:
    """A saved provider configuration."""

    name: str
    provider_type: str  # e.g. "anthropic", "openai", "openai_compatible"
    model: str
    api_key: str | None = None  # may be a secret:// URI or a plain key
    base_url: str | None = None
    residency: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderProfile:
        return cls(
            name=data["name"],
            provider_type=data["provider_type"],
            model=data["model"],
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            residency=data.get("residency", {}),
        )


class ProviderProfileStore:
    """Loads, saves, and queries named provider profiles.

    Profiles are stored in a JSON file (default: ``~/.aegis/providers.json``).
    The file is created on first write; the parent directory is created if
    needed.
    """

    DEFAULT_PATH: Path = Path.home() / ".aegis" / "providers.json"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or self.DEFAULT_PATH
        self._profiles: dict[str, ProviderProfile] = {}
        self._default: str | None = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def load(self) -> None:
        """Load profiles from disk (no-op if file does not yet exist)."""
        self._loaded = True
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._default = raw.get("default")
        self._profiles = {
            name: ProviderProfile.from_dict(data)
            for name, data in raw.get("profiles", {}).items()
        }

    def save(self) -> None:
        """Persist all profiles to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "profiles": {name: p.to_dict() for name, p in self._profiles.items()},
        }
        if self._default is not None:
            payload["default"] = self._default
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, profile: ProviderProfile, *, overwrite: bool = False) -> None:
        """Add *profile* to the store.

        Args:
            profile: The profile to add.
            overwrite: If True, replace an existing profile with the same name.

        Raises:
            ValueError: If a profile with the same name already exists and
                *overwrite* is False.
        """
        self._ensure_loaded()
        if profile.name in self._profiles and not overwrite:
            raise ValueError(
                f"Profile '{profile.name}' already exists. "
                "Pass overwrite=True or choose a different name."
            )
        self._profiles[profile.name] = profile
        if not self._profiles or len(self._profiles) == 1:
            self._default = profile.name
        self.save()

    def get(self, name: str) -> ProviderProfile:
        """Return the profile named *name*.

        Raises:
            AegisProviderNotFoundError: If no such profile exists (AEG-PRV-005).
        """
        self._ensure_loaded()
        p = self._profiles.get(name)
        if p is None:
            raise AegisProviderNotFoundError(
                f"No provider profile named '{name}'.",
                name=name,
            )
        return p

    def list_profiles(self) -> list[ProviderProfile]:
        """Return all profiles sorted by name."""
        self._ensure_loaded()
        return sorted(self._profiles.values(), key=lambda p: p.name)

    def remove(self, name: str) -> None:
        """Remove the profile named *name*.

        Raises:
            AegisProviderNotFoundError: If no such profile exists (AEG-PRV-005).
        """
        self._ensure_loaded()
        if name not in self._profiles:
            raise AegisProviderNotFoundError(
                f"No provider profile named '{name}'.",
                name=name,
            )
        del self._profiles[name]
        if self._default == name:
            self._default = next(iter(self._profiles), None)
        self.save()

    def set_default(self, name: str) -> None:
        """Set *name* as the default provider.

        Raises:
            AegisProviderNotFoundError: If no such profile exists (AEG-PRV-005).
        """
        self._ensure_loaded()
        if name not in self._profiles:
            raise AegisProviderNotFoundError(
                f"No provider profile named '{name}'.",
                name=name,
            )
        self._default = name
        self.save()

    def get_default(self) -> str | None:
        """Return the name of the default profile, or None if none is set."""
        self._ensure_loaded()
        return self._default
