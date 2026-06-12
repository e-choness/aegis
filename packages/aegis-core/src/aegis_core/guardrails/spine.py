"""GuardNode — verdict spine integrating guardrails as a PipelineNode.

Aggregation rules (PROJECT_SPEC §4):
- first ``block`` short-circuits the stage immediately
- ``sanitize`` deltas compose in order (each guard sees the sanitized state)
- ``require_approval`` pauses immediately
- every verdict (including ``allow``) is appended as a RunEvent
"""

from __future__ import annotations

from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.providers.models import Message


class GuardNode:
    """A :class:`~aegis_core.pipeline.protocol.PipelineNode` that runs an
    ordered list of :class:`~aegis_core.guardrails.protocol.Guardrail` instances.

    Designed to be placed in ``ingress`` or ``egress`` of
    :class:`~aegis_core.pipeline.assembler.PipelineAssembler`.
    """

    def __init__(self, guards: list[Guardrail], name: str = "guard") -> None:
        self.name = name
        self._guards = guards

    @property
    def guards(self) -> list[Guardrail]:
        """Public read-only view of the guards list."""
        return list(self._guards)

    @property
    def stream_capability(self) -> str:
        """Return ``"true_streaming"`` if all guards are incremental, else ``"buffered"``."""
        from aegis_core.guardrails.incremental import IncrementalGuardrail

        for guard in self._guards:
            if not isinstance(guard, IncrementalGuardrail):
                return "buffered"
        return "true_streaming"

    async def run(self, state: RunState) -> RunStateDelta:
        current_messages = list(state.messages)
        events: list[RunEvent] = []
        sanitized = False

        for guard in self._guards:
            # Build scan state with (possibly sanitized) messages from prior guards.
            scan_state = RunState(
                run_id=state.run_id,
                route=state.route,
                messages=current_messages,
                principal=state.principal,
                labels=state.labels,
                mask_map=state.mask_map,
            )
            verdict = await guard.scan(scan_state)

            events.append(
                RunEvent(
                    stage="guard",
                    node=guard.name,
                    event_type="verdict",
                    data={
                        "verdict": verdict.kind.value,
                        "guard": guard.name,
                        "reason": verdict.reason,
                    },
                )
            )

            if verdict.is_block:
                return RunStateDelta(status="blocked", events=events)

            if verdict.is_require_approval:
                return RunStateDelta(status="paused", events=events)

            if verdict.is_sanitize:
                replacement = verdict.replacement or ""
                current_messages = [
                    Message(role=m.role, content=replacement)
                    for m in current_messages
                ]
                sanitized = True

            # allow → continue to next guard

        return RunStateDelta(
            events=events,
            messages=current_messages if sanitized else None,
        )
