"""PiiUnmaskNode — restores original PII values in the model response."""

from __future__ import annotations

from aegis_core.pipeline.state import RunState, RunStateDelta


class PiiUnmaskNode:
    """A :class:`~aegis_core.pipeline.protocol.PipelineNode` that restores the
    original PII values in the model response.

    Reads ``state.mask_map`` (populated by :class:`~aegis_pack_pii.PiiMaskNode`)
    and replaces each placeholder token in ``state.response`` with its original
    value.  If there is no response or no mask map, returns an empty delta.

    Place this node in the ``egress`` stage of the pipeline assembler.
    """

    name: str = "pii_unmask_node"

    async def run(self, state: RunState) -> RunStateDelta:
        """Unmask placeholders in the response using the run's mask_map."""
        if not state.mask_map or state.response is None:
            return RunStateDelta()

        unmasked = state.response
        for placeholder, original in state.mask_map.items():
            unmasked = unmasked.replace(placeholder, original)

        return RunStateDelta(response=unmasked)
