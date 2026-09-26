"""Pack factory for aegis.classification — registered under aegis.packs entry-point group."""

from __future__ import annotations

from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline.protocol import PipelineNode


def from_config(name: str, cfg: GuardrailConfig) -> dict[str, list[PipelineNode]]:
    """Return a ClassificationNode in the ingress stage."""
    from aegis_pack_classification.node import ClassificationNode

    return {"ingress": [ClassificationNode(name=name)]}
