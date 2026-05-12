from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Dict, Literal, Optional

logger = logging.getLogger("aegis.auth_manager")


@dataclass
class AuthConfig:
    """Tier 2 authentication configuration."""
    auth_type: Literal["api_key", "mtls"]
    # For API key auth
    token: Optional[str] = None
    header_format: str = "Authorization: Bearer {token}"
    # For mTLS auth
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    verify_hostname: bool = True


class AuthManager:
    """
    Tier 2 authentication injection (Bearer token or mTLS).
    Handles both API key and mTLS-based authentication.
    """

    def __init__(self, auth_config: AuthConfig):
        self._auth_type = auth_config.auth_type
        self._token = auth_config.token
        self._header_format = auth_config.header_format
        self._cert_path = auth_config.cert_path
        self._key_path = auth_config.key_path
        self._ca_path = auth_config.ca_path
        self._verify_hostname = auth_config.verify_hostname

        logger.info("AuthManager initialized with auth_type=%s", auth_config.auth_type)

        # Validate mTLS paths if configured
        if self._auth_type == "mtls":
            self._validate_mtls_paths()

    def _validate_mtls_paths(self) -> None:
        """Validate that mTLS certificate paths exist and are readable."""
        if not self._cert_path or not os.path.exists(self._cert_path):
            logger.warning("mTLS cert path not found: %s", self._cert_path)

        if not self._key_path or not os.path.exists(self._key_path):
            logger.warning("mTLS key path not found: %s", self._key_path)

        if not self._ca_path or not os.path.exists(self._ca_path):
            logger.warning("mTLS CA path not found: %s", self._ca_path)

        logger.info("mTLS paths validated (verify_hostname=%s)", self._verify_hostname)

    def inject_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Add Bearer token or mTLS client cert to request headers.
        Returns updated headers dict.
        """
        if self._auth_type == "api_key" and self._token:
            auth_header = self._header_format.format(token=self._token)
            headers["Authorization"] = auth_header
            logger.debug("Bearer token injected into headers")
        elif self._auth_type == "mtls":
            logger.debug("mTLS authentication configured (certs will be passed to client)")

        return headers

    def get_mtls_certs(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get mTLS certificate paths for httpx client.
        Returns (cert_path, key_path, ca_path) or (None, None, None) if not configured.
        """
        if self._auth_type != "mtls":
            return (None, None, None)

        return (self._cert_path, self._key_path, self._ca_path)

    def validate_tier2_cert(self) -> bool:
        """
        Verify Tier 2 certificate against Root CA (mTLS only).
        In production, this would use cryptography lib to verify cert chain.
        For now, just check that paths exist.
        """
        if self._auth_type != "mtls":
            return True

        if not all([self._cert_path, self._key_path, self._ca_path]):
            logger.error("mTLS not fully configured (missing paths)")
            return False

        # Check paths exist
        paths_exist = all(
            os.path.exists(p) for p in [self._cert_path, self._key_path, self._ca_path]
        )

        if not paths_exist:
            logger.error("One or more mTLS paths do not exist")
            return False

        logger.info("mTLS certificate paths validated")
        return True

    def is_mtls_enabled(self) -> bool:
        """Check if mTLS is the active auth method."""
        return self._auth_type == "mtls"

    def is_api_key_enabled(self) -> bool:
        """Check if API key is the active auth method."""
        return self._auth_type == "api_key"
