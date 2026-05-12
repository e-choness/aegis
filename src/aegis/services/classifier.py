from __future__ import annotations
import re
from ..models import DataClassification


class DataClassifier:
    """
    Classifies prompt text by data sensitivity before routing.
    Regex-only for <1ms latency and zero false negatives on known patterns.
    ML second-pass planned for Phase 3 to catch obfuscated PII.
    """

    PATTERNS: dict[str, list[str]] = {
        DataClassification.RESTRICTED: [
            r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b",      # Canadian SIN
            r"\b(?:\d{4}[-\s]?){3}\d{4}\b",            # Credit card numbers
            r"\baccount[_-]?number\b",                  # Account reference keyword
            r"\b\d{9,12}\b",                            # Generic account number pattern
        ],
        DataClassification.CONFIDENTIAL: [
            r"[a-zA-Z0-9._%+-]+@(?:internal|company|corp)\.(?:com|ca)",
            r"\bapi[_-]?key\b",
            r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",         # JWT/bearer tokens
            r"\b(?:password|passwd|secret)\s*[:=]",
        ],
    }

    def classify(self, text: str) -> str:
        for level in (DataClassification.RESTRICTED, DataClassification.CONFIDENTIAL):
            if any(re.search(p, text, re.IGNORECASE) for p in self.PATTERNS[level]):
                return level
        return DataClassification.INTERNAL
