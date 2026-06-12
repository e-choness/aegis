"""RunState, RunStateDelta, and RunEvent — the pipeline's shared state objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegis_core.providers.models import Message, UsageInfo


@dataclass
class RunEvent:
    """A single append-only audit/verdict event."""

    stage: str
    node: str
    event_type: str  # node_start, node_end, verdict
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "node": self.node,
            "event_type": self.event_type,
            "data": self.data,
        }


@dataclass
class RunState:
    """Mutable pipeline state threaded through every node.

    Fields map directly to PROJECT_SPEC §4.
    """

    run_id: str
    route: str
    messages: list[Message]
    principal: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    #: mask_map is never serialised into model-visible messages (PII pack uses it)
    mask_map: dict[str, str] = field(default_factory=dict)
    events: list[RunEvent] = field(default_factory=list)
    usage: UsageInfo = field(default_factory=UsageInfo)
    response: str | None = None
    status: str = "running"  # running | completed | blocked | paused | denied
    #: Populated when status=="paused"; carries the interrupt prompt/metadata.
    interrupt_value: dict[str, object] | None = None


@dataclass
class RunStateDelta:
    """Partial update returned by a PipelineNode.run() call.

    None fields are ignored (not merged into RunState).
    """

    labels: dict[str, str] | None = None
    mask_map: dict[str, str] | None = None
    events: list[RunEvent] | None = None
    usage: UsageInfo | None = None
    response: str | None = None
    status: str | None = None
    messages: list[Message] | None = None
