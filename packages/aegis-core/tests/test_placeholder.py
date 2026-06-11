"""Placeholder smoke test for aegis-core."""

import aegis_core


def test_aegis_core_importable() -> None:
    assert aegis_core.__version__ == "2.0.0a0"
