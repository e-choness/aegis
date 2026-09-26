"""What counts as PII, and how sure we need to be — shared by masking and detect mode.

Presidio's defaults detect every entity it knows at any confidence, which
masks far too much: weekday names and "quarterly" as ``DATE_TIME``, "Q3" as a
driver's licence, email fragments as ``URL``. :class:`PiiDetector` narrows that
to identifying entities above a confidence threshold, with an allow-list for
terms that must never be masked (product names, your own company).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

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
    "UK_NINO",
    "CA_SIN",
    "MEDICAL_LICENSE",
)

#: Minimum Presidio confidence. Phone numbers without context score 0.40, so
#: raising this above 0.4 silently stops masking them.
DEFAULT_THRESHOLD = 0.4

ALL_ENTITIES = "ALL"


def deduplicate(results: Iterable[Any]) -> list[Any]:
    """Keep one detection per text span.

    Presidio may report overlapping results (an ``EMAIL_ADDRESS`` and a ``URL``
    inside it; a SIN that also looks like a phone number). The widest span
    wins; for identical spans, the most confident entity wins. Contained
    spans are dropped so right-to-left replacement stays positionally valid.
    """
    ranked = sorted(results, key=lambda r: (r.end - r.start, r.score), reverse=True)
    kept: list[Any] = []
    for r in ranked:
        if not any(k.start <= r.start and k.end >= r.end for k in kept):
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
    """

    entities: tuple[str, ...] | None = DEFAULT_ENTITIES
    threshold: float = DEFAULT_THRESHOLD
    allow_list: tuple[str, ...] = ()

    @classmethod
    def from_options(
        cls,
        entities: str | Sequence[str] | None = None,
        threshold: float | None = None,
        allow_list: Sequence[str] | None = None,
    ) -> PiiDetector:
        """Build from ``aegis.yaml`` options, validating entity names.

        ``entities: ALL`` enables every supported recognizer; omitting it uses
        :data:`DEFAULT_ENTITIES`.
        """
        if threshold is not None and not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be between 0 and 1, got {threshold}")

        chosen: tuple[str, ...] | None
        if entities is None:
            chosen = DEFAULT_ENTITIES
        elif isinstance(entities, str):
            if entities.upper() != ALL_ENTITIES:
                raise ValueError(f"entities must be a list or {ALL_ENTITIES!r}, got {entities!r}")
            chosen = None
        else:
            chosen = tuple(e.upper() for e in entities)
            from aegis_pack_pii._engine import get_analyzer

            supported = set(get_analyzer().get_supported_entities())
            unknown = sorted(set(chosen) - supported)
            if unknown:
                raise ValueError(
                    f"unknown PII entities {unknown}; supported: {', '.join(sorted(supported))}"
                )

        return cls(
            entities=chosen,
            threshold=DEFAULT_THRESHOLD if threshold is None else threshold,
            allow_list=tuple(allow_list or ()),
        )

    def find(self, text: str) -> list[Any]:
        """Return de-duplicated Presidio results for *text*."""
        from aegis_pack_pii._engine import get_analyzer

        results = get_analyzer().analyze(
            text=text,
            language="en",
            entities=list(self.entities) if self.entities is not None else None,
            score_threshold=self.threshold,
            allow_list=list(self.allow_list) or None,
        )
        return deduplicate(results)
