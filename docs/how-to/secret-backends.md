# How-to: Secret backends

Aegis resolves `secret://` URIs at config load time. Credentials are never
persisted, never appear in `repr`, and never enter logs. All credentials are
typed `SecretStr`.

## URI format

```
secret://<backend>/<path>#<key>
```

Examples:

```yaml
api_key: secret://env/ANTHROPIC_API_KEY
api_key: secret://keyring/aegis/anthropic#api_key
api_key: secret://vault/secret/aegis/prod#anthropic_key
```

## Built-in backends

### Environment variables (`env`)

```yaml
api_key: secret://env/ANTHROPIC_API_KEY
```

Reads `os.environ["ANTHROPIC_API_KEY"]`. `.env` files are loaded automatically
if `python-dotenv` is installed.

### OS keychain (`keyring`)

```yaml
api_key: secret://keyring/aegis/my-service
```

Uses the OS keychain via the `keyring` library. Ideal for developer machines.
Set the value with:

```bash
aegis keys create       # for Aegis virtual keys
python -c "import keyring; keyring.set_password('aegis', 'my-service', 'value')"
```

## Plugin backends (adopt as extras)

Vault, AWS Secrets Manager, GCP Secret Manager, and Azure Key Vault are
available as plugin adapters (`SecretProvider` implementations). Install the
relevant extra and declare it in `aegis.yaml`:

```yaml
secrets:
  backend: vault
  vault_addr: https://vault.internal
  vault_token: secret://env/VAULT_TOKEN
```

## Writing a custom backend

Implement the `SecretProvider` protocol:

```python
from pydantic import SecretStr

from aegis_core.secrets import SecretRef


class MyBackend:
    scheme = "mybackend"

    def resolve(self, ref: SecretRef) -> SecretStr:
        raw = fetch_from_my_system(ref.path, ref.key)  # noqa: F821
        return SecretStr(raw)
```

Register it via the `aegis.secrets` entry point in `pyproject.toml`.

## Security notes

- Resolved secret values are stored only as `SecretStr` for the lifetime of the process.
- `aegis config show` redacts all secrets with `**REDACTED**`.
- Secrets never appear in OpenTelemetry spans or audit log events.
