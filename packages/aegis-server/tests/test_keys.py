"""KeyStore unit tests — lifecycle, hash-only storage."""

from __future__ import annotations

import hashlib

from aegis_server.keys import KeyStore


def test_create_returns_aeg_prefixed_plaintext() -> None:
    store = KeyStore()
    key = store.create(principal_id="alice")
    assert key.startswith("aeg-")
    assert len(key) == 4 + 64  # "aeg-" + 64 hex chars


def test_only_hash_stored_not_plaintext() -> None:
    store = KeyStore()
    key = store.create(principal_id="alice")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    # Hash must be present as the index key
    assert key_hash in store._data
    # Plaintext must NOT appear in any stored value
    for entry in store._data.values():
        for v in entry.values():
            assert key not in str(v)


def test_lookup_valid_key_returns_principal() -> None:
    store = KeyStore()
    key = store.create(principal_id="bob", team="eng")
    principal = store.lookup(key)
    assert principal is not None
    assert principal.id == "bob"
    assert principal.team == "eng"


def test_lookup_invalid_key_returns_none() -> None:
    store = KeyStore()
    assert store.lookup("aeg-" + "0" * 64) is None


def test_lookup_unknown_format_returns_none() -> None:
    store = KeyStore()
    store.create(principal_id="carol")
    assert store.lookup("not-a-valid-key") is None


def test_revoke_removes_key() -> None:
    store = KeyStore()
    key = store.create(principal_id="carol")
    entries = store.list()
    assert len(entries) == 1
    key_id = str(entries[0]["key_id"])
    assert store.revoke(key_id) is True
    assert store.lookup(key) is None
    assert store.list() == []


def test_revoke_nonexistent_returns_false() -> None:
    store = KeyStore()
    assert store.revoke("key-nonexistent") is False


def test_list_does_not_expose_hash_or_plaintext() -> None:
    store = KeyStore()
    key = store.create(principal_id="dave")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    entries = store.list()
    assert len(entries) == 1
    entry_str = str(entries[0])
    assert key not in entry_str
    assert key_hash not in entry_str


def test_create_multiple_keys() -> None:
    store = KeyStore()
    k1 = store.create(principal_id="u1")
    k2 = store.create(principal_id="u2")
    assert k1 != k2
    assert len(store.list()) == 2
