"""serve() without auth raises AEG-SRV-001 unless --no-auth."""

from __future__ import annotations

import pytest

from aegis_server.app import AEGServError, create_app


def test_serve_without_auth_raises(executor: object) -> None:
    with pytest.raises(AEGServError, match="AEG-SRV-001"):
        create_app(executor)  # no authenticator, no no_auth flag


def test_serve_with_no_auth_flag_succeeds(executor: object) -> None:
    app = create_app(executor, no_auth=True)
    assert app is not None


def test_serve_with_explicit_authenticator_succeeds(executor: object) -> None:
    from aegis_server.auth import NoneAuthenticator

    app = create_app(executor, authenticator=NoneAuthenticator())
    assert app is not None


def test_serve_error_message_contains_code(executor: object) -> None:
    with pytest.raises(AEGServError) as exc_info:
        create_app(executor)
    assert "AEG-SRV-001" in str(exc_info.value)
