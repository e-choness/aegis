"""LlmGuardAdapter — wraps an llm-guard input scanner as a Guardrail."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class LlmGuardAdapter:
    """A :class:`~aegis_core.guardrails.protocol.Guardrail` that delegates to an
    `llm-guard <https://llm-guard.com/>`_ input scanner.

    The scanner is loaded lazily from ``llm_guard.input_scanners`` so that the
    ``[llm-guard]`` optional extra is only required at runtime, not at import
    time.

    Args:
        scanner_name: Class name of the llm-guard input scanner to use.
            Defaults to ``"PromptInjection"``.
        threshold: Risk-score threshold above which the scan is considered a
            violation.  Passed as ``threshold=`` to the scanner constructor.

    Requires the ``[llm-guard]`` extra (``llm-guard``).
    """

    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(
        self,
        scanner_name: str = "PromptInjection",
        threshold: float = 0.8,
    ) -> None:
        self.name: str = f"llm_guard.{scanner_name}"
        self._scanner_name = scanner_name
        self._threshold = threshold

    async def scan(self, state: RunState) -> Verdict:
        """Run the llm-guard scanner against the last user message."""
        import importlib

        module = importlib.import_module("llm_guard.input_scanners")
        scanner_cls = getattr(module, self._scanner_name)
        scanner = scanner_cls(threshold=self._threshold)

        text = state.messages[-1].content if state.messages else ""
        _sanitized, is_valid, score = scanner.scan(text, text)

        if not is_valid:
            return Verdict.block(
                f"llm_guard.{self._scanner_name}: risk_score={score:.2f}"
            )
        return Verdict.allow()
