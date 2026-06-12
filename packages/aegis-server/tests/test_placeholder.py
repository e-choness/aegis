"""Placeholder smoke test for aegis-server."""

import aegis_server


def test_aegis_server_importable() -> None:
    assert aegis_server.__version__ == "2.0.0a0"
