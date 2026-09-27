"""PiiUnmaskNode — restores original PII values in the model response."""

from __future__ import annotations

from aegis_core.masking import UnmaskNode


class PiiUnmaskNode(UnmaskNode):
    """Egress node that restores masked values in the model response.

    Reads ``state.mask_map`` (populated by :class:`~aegis_pack_pii.PiiMaskNode`
    or any other masking pack) and replaces each placeholder in
    ``state.response`` with its original value.
    """

    name: str = "pii_unmask_node"
