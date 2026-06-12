"""EnvSecretProvider — resolves secrets from environment variables.

URI format: ``secret://env/<VAR_NAME>#value``

The ``<path>`` component is used as the environment variable name.
The ``<key>`` fragment is currently ignored for env secrets (the full
env value is the secret); this keeps the URI shape consistent with
other backends that may have multiple keys per path.
"""

from __future__ import annotations

import os

from pydantic import SecretStr

from aegis_core.errors import AegisSecretRefError
from aegis_core.secrets.ref import SecretRef


class EnvSecretProvider:
    """Reads secrets from environment variables (and optionally a .env file)."""

    scheme: str = "env"

    def resolve(self, ref: SecretRef) -> SecretStr:
        """Return the value of the environment variable named by *ref.path*.

        Raises ``AegisSecretRefError`` if the variable is not set.
        """
        env_var = ref.path
        value = os.environ.get(env_var)
        if value is None:
            raise AegisSecretRefError(
                f"Environment variable {env_var!r} not set (required by {ref.raw!r}).",
                uri=ref.raw,
                env_var=env_var,
            )
        return SecretStr(value)
