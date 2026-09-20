"""Shared fixtures for aegis-server tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from starlette.testclient import TestClient

from aegis_core.pipeline.executor import PipelineExecutor
from aegis_core.testing.providers import FakeProvider
from aegis_server.app import create_app
from aegis_server.auth import ApiKeyAuthenticator
from aegis_server.keys import KeyStore
from aegis_server.store.ledger import InMemoryLedgerStore


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider(complete_response="hello from aegis")


@pytest.fixture
def executor(fake_provider: FakeProvider) -> PipelineExecutor:
    ex = PipelineExecutor()
    ex.register("default", provider=fake_provider)
    return ex


@pytest.fixture
def key_store() -> KeyStore:
    return KeyStore()  # in-memory, no path


@pytest.fixture
def valid_key(key_store: KeyStore) -> str:
    return key_store.create(principal_id="test-user", team="test-team")


@pytest.fixture
def client(executor: PipelineExecutor, key_store: KeyStore, valid_key: str) -> TestClient:
    auth = ApiKeyAuthenticator(key_store)
    app = create_app(executor, authenticator=auth)
    # valid_key consumed here to ensure it is created in key_store before the client
    _ = valid_key
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_no_auth(executor: PipelineExecutor) -> TestClient:
    app = create_app(executor, no_auth=True)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def client_with_ledger(executor: PipelineExecutor) -> Generator[TestClient, None, None]:
    """Client with InMemoryLedgerStore wired; uses generator form so lifespan fires."""
    ledger = InMemoryLedgerStore()
    app = create_app(
        executor,
        no_auth=True,
        ledger_store=ledger,
        config_digest="sha256:test",
        route_metadata={"default": {"description": "test route", "risk_rating": "low"}},
    )
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture
def client_with_digest(executor: PipelineExecutor) -> TestClient:
    """Client with config_digest and config_path wired (Phase 0)."""
    app = create_app(
        executor,
        no_auth=True,
        config_digest="sha256:abc123",
        config_path="/etc/aegis/aegis.yaml",
    )
    return TestClient(app, raise_server_exceptions=True)
