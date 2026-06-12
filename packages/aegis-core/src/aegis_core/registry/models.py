"""Plugin registry data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    """Metadata for a discovered plugin entry point."""

    name: str
    group: str
    value: str  # entry-point value string, e.g. "my_pkg.module:MyClass"
    dist_name: str = ""  # distribution package name
    dist_version: str = ""  # distribution package version
    loaded: bool = field(default=False, compare=False)

    @property
    def module_path(self) -> str:
        """Return the module portion of the entry-point value."""
        return self.value.split(":")[0] if ":" in self.value else self.value

    @property
    def attr(self) -> str | None:
        """Return the attribute portion of the entry-point value, if any."""
        parts = self.value.split(":", 1)
        return parts[1] if len(parts) == 2 else None
