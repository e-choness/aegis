"""PiiMaskGuard — blocks requests/responses that contain PII."""

from __future__ import annotations

from typing import ClassVar, Literal

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


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

    async def scan(self, state: RunState) -> Verdict:
        """Scan all messages; block if any PII entity is found."""
        from aegis_pack_pii._engine import get_analyzer

        analyzer = get_analyzer()
        for msg in state.messages:
            results = analyzer.analyze(text=msg.content, language="en")
            if results:
                types = sorted({r.entity_type for r in results})
                return Verdict.block(f"PII detected: {', '.join(types)}")
        return Verdict.allow()
