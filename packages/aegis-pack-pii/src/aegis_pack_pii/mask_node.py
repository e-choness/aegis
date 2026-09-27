"""PiiMaskNode — replaces PII in messages with placeholders before the provider."""

from __future__ import annotations

from aegis_core.masking import mask_messages
from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_pack_pii.detection import PiiDetector


class PiiMaskNode:
    """A :class:`~aegis_core.pipeline.protocol.PipelineNode` that masks PII in
    all messages before they reach the model.

    Placeholders (e.g. ``<EMAIL_ADDRESS_0>``) replace detected entities, using
    the shared scheme in :mod:`aegis_core.masking`. The mapping of placeholder
    → original is stored in ``RunStateDelta.mask_map`` and is NOT exposed in
    model-visible message content.

    Pair with :class:`~aegis_pack_pii.PiiUnmaskNode` in the egress stage to
    restore original values in the model's response.

    Requires the ``[pii]`` extra (``presidio-analyzer``, ``en_core_web_sm``).
    """

    name: str = "pii_mask_node"

    def __init__(self, name: str | None = None, detector: PiiDetector | None = None) -> None:
        if name is not None:
            self.name = name
        self._detector = detector or PiiDetector()

    def warmup(self) -> None:
        """Load the NLP models at startup (called by the server)."""
        self._detector.warmup()

    async def run(self, state: RunState) -> RunStateDelta:
        """Mask PII in all messages; return updated messages and mask_map."""
        return mask_messages(state, self._detector.find, node=self.name)
