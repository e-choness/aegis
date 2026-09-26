"""Placeholder smoke test for aegis-core."""

from importlib.metadata import version

import aegis_core


def test_aegis_core_importable() -> None:
    assert aegis_core.__version__ == version("aegis-gateway-core")
