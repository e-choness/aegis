from __future__ import annotations
import logging
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

logger = logging.getLogger("aegis.pii")

_NLP_CONFIG = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}


def _build_analyzer() -> AnalyzerEngine:
    provider = NlpEngineProvider(nlp_configuration=_NLP_CONFIG)
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    # Canadian SIN is not in Presidio's default registry
    sin_recognizer = PatternRecognizer(
        supported_entity="CA_SIN",
        supported_language="en",
        patterns=[
            Pattern("sin_dashes", r"\b\d{3}-\d{3}-\d{3}\b", 0.90),
            Pattern("sin_spaces", r"\b\d{3}\s\d{3}\s\d{3}\b", 0.85),
            Pattern("sin_plain",  r"\b\d{9}\b",               0.60),
        ],
    )
    analyzer.registry.add_recognizer(sin_recognizer)
    return analyzer


class PIIMasker:
    """
    Detects and masks PII before prompts reach any provider.
    Uses Presidio with a custom CA_SIN recognizer for PIPEDA compliance.
    Phase 3 upgrade: add ML NER second-pass to catch obfuscated PII.

    mask() works right-to-left so span replacements don't shift earlier offsets.
    """

    def __init__(self) -> None:
        self._analyzer = _build_analyzer()

    def mask(self, text: str) -> tuple[str, dict[str, str]]:
        """
        Returns (masked_text, restore_map).
        restore_map: placeholder → original value, used by unmask().
        """
        results = self._analyzer.analyze(text=text, language="en")
        sorted_results = sorted(results, key=lambda r: r.start, reverse=True)

        restore_map: dict[str, str] = {}
        masked = text
        for i, result in enumerate(sorted_results):
            placeholder = f"<{result.entity_type}_{i}>"
            restore_map[placeholder] = text[result.start:result.end]
            masked = masked[:result.start] + placeholder + masked[result.end:]

        if restore_map:
            entity_types = sorted({r.entity_type for r in results})
            logger.info("PII masked in prompt: %s", entity_types)

        return masked, restore_map

    def unmask(self, text: str, restore_map: dict[str, str]) -> str:
        """Restores original values in the provider response."""
        for placeholder, original in restore_map.items():
            text = text.replace(placeholder, original)
        return text

    def scan_output(self, text: str) -> list[str]:
        """Returns entity types found in output. Non-empty signals potential PII leakage."""
        results = self._analyzer.analyze(text=text, language="en")
        entity_types = [r.entity_type for r in results]
        if entity_types:
            logger.warning("PII detected in provider output: %s", sorted(set(entity_types)))
        return entity_types
