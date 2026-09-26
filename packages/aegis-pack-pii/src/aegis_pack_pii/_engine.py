"""Shared Presidio AnalyzerEngine singleton for the PII pack."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine as _AE

_analyzer: _AE | None = None


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _canadian_sin_recognizer() -> object:
    """Canadian Social Insurance Number: 9 digits, Luhn-checked.

    Presidio ships no recognizer for it; without one a SIN is either missed
    or mislabelled as a phone number.
    """
    from presidio_analyzer import Pattern, PatternRecognizer

    class CanadianSinRecognizer(PatternRecognizer):
        def validate_result(self, pattern_text: str) -> bool:
            digits = "".join(c for c in pattern_text if c.isdigit())
            return len(digits) == 9 and _luhn_valid(digits)

    return CanadianSinRecognizer(
        supported_entity="CA_SIN",
        patterns=[
            Pattern("CA_SIN (formatted)", r"\b\d{3}[- ]\d{3}[- ]\d{3}\b", 0.5),
            Pattern("CA_SIN (unformatted)", r"\b\d{9}\b", 0.1),
        ],
        context=["sin", "social insurance", "assurance sociale", "nas"],
    )


def get_analyzer() -> _AE:
    """Return the cached AnalyzerEngine, initialising it on first call.

    Requires the ``[pii]`` extra (``presidio-analyzer`` + ``en_core_web_sm``).
    """
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine

        engine = AnalyzerEngine()
        engine.registry.add_recognizer(_canadian_sin_recognizer())  # type: ignore[arg-type]
        _analyzer = engine
    return _analyzer
