"""PiiMaskGuard — blocks requests/responses that contain PII."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_pack_pii.detection import PiiDetector


class PiiMaskGuard:
    """A :class:`~aegis_core.guardrails.protocol.Guardrail` that blocks content
    containing personally-identifiable information detected by Presidio.

    Useful as an egress guard to prevent the model response from leaking PII,
    or as an ingress guard to enforce a no-PII policy on user messages.

    For the mask → model → unmask round trip, use :class:`~aegis_pack_pii.PiiMaskNode`
    together with :class:`~aegis_pack_pii.PiiUnmaskNode` instead.

    Requires the ``[pii]`` extra (``presidio-analyzer``, ``en_core_web_sm``).
    """

    name: str = "pii_mask"
    streaming: ClassVar[Literal["none", "incremental"]] = "none"

    def __init__(self, detector: PiiDetector | None = None, name: str | None = None) -> None:
        self._detector = detector or PiiDetector()
        if name is not None:
            self.name = name

    async def scan(self, state: RunState) -> Verdict:
        """Scan all messages; block if any PII entity is found."""
        for msg in state.messages:
            results = self._detector.find(msg.content)
            if results:
                types = sorted({r.entity_type for r in results})
                return Verdict.block(f"PII detected: {', '.join(types)}")
        return Verdict.allow()
