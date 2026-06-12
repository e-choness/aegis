"""Tests for aegis_core.secrets — SecretRef parsing, backends, resolver."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from aegis_core.errors import AegisSecretBackendError, AegisSecretRefError
from aegis_core.secrets import (
    EnvSecretProvider,
    KeyringSecretProvider,
    SecretRef,
    SecretResolver,
)
from aegis_core.secrets.backends.keyring import InMemoryKeyring

# ── SecretRef ──────────────────────────────────────────────────────────────────


def test_parse_env_uri() -> None:
    ref = SecretRef.parse("secret://env/MY_VAR#value")
    assert ref.scheme == "env"
    assert ref.path == "MY_VAR"
    assert ref.key == "value"


def test_parse_keyring_uri() -> None:
    ref = SecretRef.parse("secret://keyring/aegis/anthropic#api_key")
    assert ref.scheme == "keyring"
    assert ref.path == "aegis/anthropic"
    assert ref.key == "api_key"


def test_parse_bad_uri_raises() -> None:
    with pytest.raises(AegisSecretRefError) as exc_info:
        SecretRef.parse("not-a-secret-uri")
    assert "AEG-CFG-010" in str(exc_info.value)


def test_parse_missing_fragment_raises() -> None:
    with pytest.raises(AegisSecretRefError):
        SecretRef.parse("secret://env/MY_VAR")


def test_is_secret_uri_true() -> None:
    assert SecretRef.is_secret_uri("secret://env/FOO#v") is True


def test_is_secret_uri_false() -> None:
    assert SecretRef.is_secret_uri("plain-string") is False


def test_secret_ref_repr_has_no_secret_value() -> None:
    """SecretRef.__repr__ must not include the resolved secret."""
    ref = SecretRef.parse("secret://env/SOME_VAR#value")
    r = repr(ref)
    # Repr shows structural info, not a resolved value
    assert "SOME_VAR" in r
    assert "secret://" not in r  # resolved form not in repr is fine


# ── EnvSecretProvider ─────────────────────────────────────────────────────────


def test_env_provider_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_TEST_SECRET_ENV", "hello-world")
    provider = EnvSecretProvider()
    ref = SecretRef.parse("secret://env/_TEST_SECRET_ENV#value")
    result = provider.resolve(ref)
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "hello-world"


def test_env_provider_missing_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("_TEST_MISSING_VAR", raising=False)
    provider = EnvSecretProvider()
    ref = SecretRef.parse("secret://env/_TEST_MISSING_VAR#value")
    with pytest.raises(AegisSecretRefError) as exc_info:
        provider.resolve(ref)
    assert "AEG-CFG-010" in str(exc_info.value)
    assert "_TEST_MISSING_VAR" in str(exc_info.value)
    assert "Fix:" in str(exc_info.value)


# ── KeyringSecretProvider (in-memory stub) ────────────────────────────────────


def test_keyring_provider_with_stub() -> None:
    """Keyring backend resolves via an in-memory stub (no OS keychain)."""
    stub = InMemoryKeyring()
    stub.set_password("aegis/service", "my_api_key", "stub-secret-value")

    provider = KeyringSecretProvider(override_backend=stub)
    ref = SecretRef.parse("secret://keyring/aegis/service#my_api_key")
    result = provider.resolve(ref)

    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "stub-secret-value"


def test_keyring_provider_missing_entry_raises() -> None:
    stub = InMemoryKeyring()
    provider = KeyringSecretProvider(override_backend=stub)
    ref = SecretRef.parse("secret://keyring/no-service#no-key")
    with pytest.raises(AegisSecretRefError) as exc_info:
        provider.resolve(ref)
    assert "AEG-CFG-010" in str(exc_info.value)
    assert "Fix:" in str(exc_info.value)


def test_keyring_stub_set_and_delete() -> None:
    """InMemoryKeyring stores and removes entries correctly."""
    stub = InMemoryKeyring()
    stub.set_password("svc", "usr", "pw")
    assert stub.get_password("svc", "usr") == "pw"
    stub.delete_password("svc", "usr")
    assert stub.get_password("svc", "usr") is None


# ── SecretResolver ────────────────────────────────────────────────────────────


def test_resolver_dispatches_to_correct_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_RESOLVER_TEST", "resolved-value")
    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    result = resolver.resolve("secret://env/_RESOLVER_TEST#value")
    assert result.get_secret_value() == "resolved-value"


def test_resolver_unknown_scheme_raises() -> None:
    resolver = SecretResolver()
    with pytest.raises(AegisSecretBackendError) as exc_info:
        resolver.resolve("secret://vault/some/path#key")
    assert "AEG-CFG-011" in str(exc_info.value)
    assert "vault" in str(exc_info.value)
    assert "Fix:" in str(exc_info.value)


def test_resolver_resolve_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_dict walks nested dicts and replaces secret:// strings."""
    monkeypatch.setenv("_DICT_SECRET", "dict-secret-value")
    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    data = {
        "providers": {
            "p1": {
                "type": "openai_compatible",
                "api_key": "secret://env/_DICT_SECRET#value",
            }
        },
        "plain_key": "not-a-secret",
    }
    result = resolver.resolve_dict(data)
    assert isinstance(result["providers"]["p1"]["api_key"], SecretStr)
    assert result["providers"]["p1"]["api_key"].get_secret_value() == "dict-secret-value"
    assert result["plain_key"] == "not-a-secret"


def test_resolver_resolve_dict_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_dict handles lists inside the config dict."""
    monkeypatch.setenv("_LIST_SECRET", "list-value")
    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    data = {"items": ["secret://env/_LIST_SECRET#value", "plain"]}
    result = resolver.resolve_dict(data)
    assert isinstance(result["items"][0], SecretStr)
    assert result["items"][1] == "plain"


def test_resolver_keyring_and_env_coexist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both env and keyring providers can be registered simultaneously."""
    monkeypatch.setenv("_COEXIST_ENV", "env-value")
    stub = InMemoryKeyring()
    stub.set_password("svc", "key", "keyring-value")

    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    resolver.register(KeyringSecretProvider(override_backend=stub))

    env_result = resolver.resolve("secret://env/_COEXIST_ENV#value")
    kr_result = resolver.resolve("secret://keyring/svc#key")

    assert env_result.get_secret_value() == "env-value"
    assert kr_result.get_secret_value() == "keyring-value"


def test_secret_str_never_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """A resolved SecretStr never leaks its value in repr."""
    monkeypatch.setenv("_REPR_SECRET", "dont-show-me")
    resolver = SecretResolver()
    resolver.register(EnvSecretProvider())
    result = resolver.resolve("secret://env/_REPR_SECRET#value")
    assert "dont-show-me" not in repr(result)
    assert "dont-show-me" not in str(result)
