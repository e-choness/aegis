"""Shared Presidio AnalyzerEngine instances for the PII pack (one per spaCy model)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine as _AE

#: spaCy model used for name/location detection. Small (~12 MB) and, for the
#: identifying entities Aegis masks by default, as accurate as en_core_web_lg.
DEFAULT_SPACY_MODEL = "en_core_web_sm"

_analyzers: dict[str, _AE] = {}


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


def ensure_model_installed(model: str) -> None:
    """Raise ``ValueError`` with the install command if *model* isn't available.

    Presidio would otherwise try to download a model at runtime — which fails
    in read-only or non-root containers and stalls the first request.
    """
    if Path(model).is_dir() or importlib.util.find_spec(model) is not None:
        return
    raise ValueError(
        f"spaCy model {model!r} is not installed — run `python -m spacy download {model}`"
    )


def get_analyzer(model: str = DEFAULT_SPACY_MODEL) -> _AE:
    """Return the cached AnalyzerEngine for *model*, creating it on first use.

    Requires the ``[pii]`` extra and the spaCy model to be installed; nothing
    is downloaded at runtime.
    """
    if model not in _analyzers:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        ensure_model_installed(model)
        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model}],
            }
        ).create_engine()
        engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        engine.registry.add_recognizer(_canadian_sin_recognizer())  # type: ignore[arg-type]
        _analyzers[model] = engine
    return _analyzers[model]
