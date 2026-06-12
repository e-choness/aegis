"""Shared Presidio AnalyzerEngine singleton for the PII pack."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine as _AE

_analyzer: _AE | None = None


def get_analyzer() -> _AE:
    """Return the cached AnalyzerEngine, initialising it on first call.

    Requires the ``[pii]`` extra (``presidio-analyzer`` + ``en_core_web_sm``).
    """
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine

        _analyzer = AnalyzerEngine()
    return _analyzer
