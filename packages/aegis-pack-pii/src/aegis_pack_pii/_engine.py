"""Shared Presidio AnalyzerEngine instances for the PII pack (one per spaCy model)."""

from __future__ import annotations

import importlib.util
import re
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


_STREET_TYPES = (
    "Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|"
    "Crescent|Cres|Place|Pl|Terrace|Highway|Hwy|Parkway|Pkwy|Circle|Cir|Square|Sq|"
    "Trail|Close|Row|Grove|Gardens|Mews"
)
_DIRECTION = r"(?:North|South|East|West|N|S|E|W|NE|NW|SE|SW)\.?"
_UNIT = r"(?:Apt|Apartment|Unit|Suite|Ste|Floor|Fl|#)\.?\s*[\w-]+"
_US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|"
    "NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)


def _address_recognizers() -> list[object]:
    """Street addresses and postal codes — places that pinpoint a household.

    A city or country identifies no one, so ``LOCATION`` is opt-in; a house
    number on a named street, or a postal code (a Canadian one covers a few
    dozen homes), does. Street words must be capitalised, so "drove 300 km
    down the highway" isn't an address.
    """
    from presidio_analyzer import Pattern, PatternRecognizer

    # Presidio matches case-insensitively by default, which would let
    # "300 km down the highway" through; case is what separates a street name.
    case_sensitive = re.DOTALL | re.MULTILINE
    street = (
        rf"(?:(?:{_UNIT})[,\s]+)?"  # Unit 12, 42 …
        r"\b\d{1,6}[A-Za-z]?(?:-\d{1,6})?\s+"  # 42, 42B, 1203-42
        rf"(?:{_DIRECTION}\s+)?"
        r"(?:(?:[A-Z][\w'.-]*|\d{1,3}(?:st|nd|rd|th))\s+){1,4}"  # Wellington, 5th
        rf"(?:{_STREET_TYPES})\b\.?"
        rf"(?:\s+{_DIRECTION}(?!\w))?"
        rf"(?:,?\s+{_UNIT})?"
    )
    # French order: 45 rue Sainte-Catherine, 1200 boulevard de Maisonneuve
    street_fr = (
        r"\b\d{1,6}[A-Za-z]?(?:-\d{1,6})?,?\s+"
        r"(?:[Rr]ue|[Cc]hemin|[Bb]oulevard|[Bb]oul\.|[Aa]venue|[Rr]oute|[Pp]lace)\s+"
        r"(?:(?:de|du|des|de la|d')\s*)?[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3}"
        rf"(?:,?\s+{_UNIT})?"
    )
    context = ["address", "ship", "deliver", "live", "lives", "reside", "mail", "home"]
    return [
        PatternRecognizer(
            supported_entity="STREET_ADDRESS",
            patterns=[
                # 0.85 — as sure as a spaCy name guess, so on overlap the wider
                # address wins over "Suite" or "King" read as a PERSON.
                Pattern("street address", street, 0.85),
                Pattern("street address (French order)", street_fr, 0.85),
                Pattern("PO box", r"(?i)\bP\.?\s?O\.?\s+Box\s+\d{1,6}\b", 0.6),
            ],
            context=context,
            global_regex_flags=case_sensitive,
        ),
        PatternRecognizer(
            supported_entity="POSTAL_CODE",
            patterns=[
                # Canada: letters D, F, I, O, Q, U never appear; W, Z never first.
                Pattern(
                    "CA postal code",
                    r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d\b",
                    0.6,
                ),
                Pattern("UK postcode", r"\b[A-Z]{1,2}\d[A-Z\d]? \d[ABD-HJLNP-UW-Z]{2}\b", 0.5),
                Pattern("US ZIP+4", r"\b\d{5}-\d{4}\b", 0.5),
                Pattern("US state + ZIP", rf"\b(?:{_US_STATES})\s+\d{{5}}\b", 0.6),
            ],
            context=["postal", "postcode", "zip", *context],
            global_regex_flags=case_sensitive,
        ),
    ]


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
        for recognizer in _address_recognizers():
            engine.registry.add_recognizer(recognizer)  # type: ignore[arg-type]
        _analyzers[model] = engine
    return _analyzers[model]
