"""Placeholder smoke test for aegis-server."""

from importlib.metadata import version

import aegis_server


def test_aegis_server_importable() -> None:
    assert aegis_server.__version__ == version("aegis-gateway-server")
