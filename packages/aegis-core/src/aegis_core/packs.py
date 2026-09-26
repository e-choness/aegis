"""Public API for pack and plugin authors.

A pack's factory is registered under the ``aegis.packs`` entry-point group and
turns one ``guardrails:`` entry of ``aegis.yaml`` into pipeline nodes::

    from aegis_core.packs import GuardrailConfig, PackNodes

    def from_config(name: str, cfg: GuardrailConfig) -> PackNodes:
        return {"ingress": [...], "egress": [...]}

Provider plugins (``aegis.providers``) may define
``from_config(name: str, cfg: ProviderConfig)``.

Import these names from here rather than from ``aegis_core.config`` — the
config package is internal, and the import-linter contract keeps packs off it.
"""

from __future__ import annotations

from collections.abc import Callable

from aegis_core.config.models import GuardrailConfig, ProviderConfig
from aegis_core.pipeline.protocol import PipelineNode

#: What a pack factory returns: stage name (``"ingress"`` / ``"egress"``) → nodes.
PackNodes = dict[str, list[PipelineNode]]

#: Signature of an ``aegis.packs`` entry point.
PackFactory = Callable[[str, GuardrailConfig], PackNodes]

__all__ = ["GuardrailConfig", "PackFactory", "PackNodes", "ProviderConfig"]
