"""Aegis structured errors — AEG-<AREA>-<NNN> format."""

from __future__ import annotations


class AegisError(Exception):
    """Base class for all Aegis framework errors.

    Every subclass must set ``code``, ``what``, ``why``, and ``fix``.
    """

    code: str = "AEG-UNK-000"
    what: str = "Unknown error"
    why: str = ""
    fix: str = ""

    def __init__(self, message: str | None = None, **context: object) -> None:
        self._context = context
        parts = [f"[{self.code}] {message or self.what}"]
        if self.why:
            parts.append(f"  Why: {self.why}")
        if self.fix:
            parts.append(f"  Fix: {self.fix}")
        if context:
            parts.append(f"  Context: {context}")
        super().__init__("\n".join(parts))


class AegisConfigError(AegisError):
    """Configuration-layer errors (AEG-CFG-*)."""

    code = "AEG-CFG-001"
    what = "Configuration error"
    why = "The aegis.yaml file is invalid or incomplete."
    fix = "Check the configuration file and correct any issues."


class AegisConfigNotFoundError(AegisConfigError):
    code = "AEG-CFG-002"
    what = "Configuration file not found"
    why = "The specified aegis.yaml path does not exist."
    fix = "Run `aegis init` to create a starter configuration, or supply the correct path."


class AegisConfigValidationError(AegisConfigError):
    code = "AEG-CFG-003"
    what = "Configuration validation failed"
    why = "One or more fields in aegis.yaml failed schema validation."
    fix = "Review the field errors below and correct the configuration."


class AegisSecretRefError(AegisConfigError):
    code = "AEG-CFG-010"
    what = "Unknown or unresolvable secret reference"
    why = "A secret:// URI in the configuration could not be resolved."
    fix = (
        "Ensure the secret URI format is `secret://<backend>/<path>#<key>` "
        "and that the backend is registered and the value exists."
    )


class AegisSecretBackendError(AegisConfigError):
    code = "AEG-CFG-011"
    what = "Secret backend not registered"
    why = "The secret backend scheme referenced in the config is not available."
    fix = "Register a SecretProvider for this scheme or use 'env' (always available)."


class AegisPluginError(AegisError):
    """Plugin registry errors (AEG-CFG-02*)."""

    code = "AEG-CFG-020"
    what = "Plugin registry error"
    why = "An error occurred while discovering or loading plugins."
    fix = "Check that all installed aegis plugins are compatible and correctly packaged."


class AegisPluginDuplicateError(AegisPluginError):
    code = "AEG-CFG-021"
    what = "Duplicate plugin name detected"
    why = "Two installed packages declare the same plugin name in the same entry-point group."
    fix = (
        "Uninstall or rename one of the conflicting plugins. "
        "Each plugin name must be unique within its group."
    )


class AegisPluginNotFoundError(AegisPluginError):
    code = "AEG-CFG-022"
    what = "Plugin not found"
    why = "No plugin with the given name was found in the specified group."
    fix = "Run `aegis plugin list` to see available plugins and check the name/group."
