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


# ---------------------------------------------------------------------------
# Provider errors (AEG-PRV-*)
# ---------------------------------------------------------------------------


class AegisProviderError(AegisError):
    """Provider-layer errors (AEG-PRV-*)."""

    code = "AEG-PRV-001"
    what = "Provider error"
    why = "The model provider returned an unexpected error."
    fix = "Check provider configuration, credentials, and the model name."


class AegisProviderAuthError(AegisProviderError):
    code = "AEG-PRV-002"
    what = "Provider authentication failed"
    why = "The API key or credentials were rejected by the provider."
    fix = "Verify the API key is correct and has not expired. Update via `aegis provider add`."


class AegisProviderRateLimitError(AegisProviderError):
    code = "AEG-PRV-003"
    what = "Provider rate limit exceeded"
    why = "The provider rejected the request due to rate limiting."
    fix = "Reduce request frequency, upgrade your plan, or configure a fallback route."


class AegisProviderTimeoutError(AegisProviderError):
    code = "AEG-PRV-004"
    what = "Provider request timed out"
    why = "The provider did not respond within the configured timeout."
    fix = "Check network connectivity, increase the timeout, or use a different provider."


class AegisProviderNotFoundError(AegisProviderError):
    code = "AEG-PRV-005"
    what = "Provider profile not found"
    why = "No provider profile with the given name exists in the profile store."
    fix = "Run `aegis provider list` to see available profiles, or add one with `aegis provider add`."


# ---------------------------------------------------------------------------
# Policy errors (AEG-POL-*)
# ---------------------------------------------------------------------------


class AegisPolicyError(AegisError):
    """Policy lint/test errors (AEG-POL-*)."""

    code = "AEG-POL-001"
    what = "Policy error"
    why = "The Aegis policy configuration is invalid."
    fix = "Check the policy configuration file and correct any issues."


class AegisPolicyBrokenRefError(AegisPolicyError):
    code = "AEG-POL-001"
    what = "Broken guardrail reference in pipeline"
    why = "The pipeline section references a guardrail name not declared in the guardrails section."
    fix = (
        "Add the guardrail to the guardrails section, "
        "or remove the reference from the pipeline."
    )


class AegisPolicyMissingPackError(AegisPolicyError):
    code = "AEG-POL-002"
    what = "Guardrail pack not installed"
    why = "The guardrail's pack module is not importable in the current environment."
    fix = "Install the pack or add it to your project dependencies."


# ---------------------------------------------------------------------------
# MCP errors (AEG-MCP-*)
# ---------------------------------------------------------------------------


class AegisMcpError(AegisError):
    """MCP-layer errors (AEG-MCP-*)."""

    code = "AEG-MCP-001"
    what = "MCP connection error"
    why = "An error occurred while connecting to or communicating with an MCP server."
    fix = "Check the MCP server URL, ensure the server is running, and verify network connectivity."


class AegisMcpToolBlockedError(AegisMcpError):
    code = "AEG-MCP-002"
    what = "Tool call blocked by guard"
    why = "A tool-call guard rejected the tool arguments before the tool was invoked."
    fix = "Review the tool call arguments and ensure they do not violate configured policies."


class AegisMcpResultBlockedError(AegisMcpError):
    code = "AEG-MCP-003"
    what = "Tool result blocked by injection guard"
    why = "The tool result contained content detected as a prompt-injection attempt."
    fix = "Review the MCP server's output and ensure tool results do not contain injection patterns."


class AegisMcpToolNotFoundError(AegisMcpError):
    code = "AEG-MCP-004"
    what = "MCP tool not found"
    why = "The requested tool name was not found in the connected MCP server."
    fix = "Verify the tool name against the server's tools/list, or check the MCP server configuration."
