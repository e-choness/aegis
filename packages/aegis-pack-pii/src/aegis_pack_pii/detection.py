"""What counts as PII, and how sure we need to be — shared by masking and detect mode.

Presidio's defaults detect every entity it knows at any confidence, which
masks far too much: weekday names and "quarterly" as ``DATE_TIME``, "Q3" as a
driver's licence, email fragments as ``URL``. :class:`PiiDetector` narrows that
to identifying entities above a confidence threshold, with an allow-list for
terms that must never be masked (product names, your own company).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from aegis_pack_pii._engine import DEFAULT_SPACY_MODEL, ensure_model_installed, get_analyzer

#: Entities that identify a person or account. Everything else Presidio knows
#: (dates, URLs, nationalities, region-specific IDs) is opt-in via ``entities:``.
DEFAULT_ENTITIES: tuple[str, ...] = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "IP_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "CRYPTO",
    "US_SSN",
    "US_ITIN",
    "US_PASSPORT",
    "US_BANK_NUMBER",
    "UK_NHS",
    "CA_SIN",
    "MEDICAL_LICENSE",
)

#: Minimum Presidio confidence. Phone numbers without context score 0.40, so
#: raising this above 0.4 silently stops masking them.
DEFAULT_THRESHOLD = 0.4

ALL_ENTITIES = "ALL"

#: A calendar date: 2026-09-26, 2026/09/26, 26/09/2026, 09-26-2026.
_DATE = re.compile(
    r"\b(?:(?:19|20)\d\d[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])"
    r"|(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|[12]\d|3[01])[-/.](?:19|20)\d\d)\b"
)


def _is_date_not_phone(result: Any, text: str) -> bool:
    """The phone recognizer is lenient: "2026-09-26 // 11" (a timestamp) parses
    as a dialable number. A phone number never contains a calendar date."""
    return result.entity_type == "PHONE_NUMBER" and bool(
        _DATE.search(text[result.start : result.end])
    )


def deduplicate(results: Iterable[Any]) -> list[Any]:
    """Keep non-overlapping detections, most confident first.

    Presidio may report overlapping results: a ``URL`` inside an
    ``EMAIL_ADDRESS``, a SIN that also looks like a phone number, or a spaCy
    ``PERSON`` guess that swallows a neighbouring email ("Email a@x.com and").
    Pattern recognizers (emails, cards, SINs — score 1.0) are more reliable
    than statistical name guesses (0.85), so the most confident detection wins
    and anything overlapping it is dropped; ties go to the wider span. The
    result never overlaps, so right-to-left replacement stays valid.
    """
    ranked = sorted(results, key=lambda r: (r.score, r.end - r.start), reverse=True)
    kept: list[Any] = []
    for r in ranked:
        if not any(k.start < r.end and r.start < k.end for k in kept):
            kept.append(r)
    return kept


@dataclass(frozen=True)
class PiiDetector:
    """Presidio analysis restricted to *entities* above *threshold*.

    Args:
        entities: Entity types to detect; ``None`` means every entity the
            analyzer supports.
        threshold: Minimum confidence score (0-1).
        allow_list: Exact strings that are never reported as PII.
        spacy_model: spaCy model used for names and locations (must be
            installed; nothing is downloaded at runtime).
    """

    entities: tuple[str, ...] | None = DEFAULT_ENTITIES
    threshold: float = DEFAULT_THRESHOLD
    allow_list: tuple[str, ...] = ()
    spacy_model: str = DEFAULT_SPACY_MODEL

    @classmethod
    def from_options(
        cls,
        entities: str | Sequence[str] | None = None,
        threshold: float | None = None,
        allow_list: Sequence[str] | None = None,
        spacy_model: str | None = None,
    ) -> PiiDetector:
        """Build from ``aegis.yaml`` options, validating entity names.

        ``entities: ALL`` enables every supported recognizer; omitting it uses
        :data:`DEFAULT_ENTITIES`.
        """
        if threshold is not None and not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be between 0 and 1, got {threshold}")
        model = spacy_model or DEFAULT_SPACY_MODEL
        ensure_model_installed(model)  # fail at startup, not on the first request

        chosen: tuple[str, ...] | None
        if entities is None:
            chosen = DEFAULT_ENTITIES
        elif isinstance(entities, str):
            if entities.upper() != ALL_ENTITIES:
                raise ValueError(f"entities must be a list or {ALL_ENTITIES!r}, got {entities!r}")
            chosen = None
        else:
            chosen = tuple(e.upper() for e in entities)
            supported = set(get_analyzer(model).get_supported_entities())
            unknown = sorted(set(chosen) - supported)
            if unknown:
                raise ValueError(
                    f"unknown PII entities {unknown}; supported: {', '.join(sorted(supported))}"
                )

        return cls(
            entities=chosen,
            threshold=DEFAULT_THRESHOLD if threshold is None else threshold,
            allow_list=tuple(allow_list or ()),
            spacy_model=model,
        )

    def find(self, text: str) -> list[Any]:
        """Return de-duplicated Presidio results for *text*."""
        results = get_analyzer(self.spacy_model).analyze(
            text=text,
            language="en",
            entities=list(self.entities) if self.entities is not None else None,
            score_threshold=self.threshold,
            allow_list=list(self.allow_list) or None,
        )
        return deduplicate(r for r in results if not _is_date_not_phone(r, text))
