"""PipelineNode Protocol — the public contract for all pipeline node implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aegis_core.pipeline.state import RunState, RunStateDelta


@runtime_checkable
class PipelineNode(Protocol):
    """Contract for a single unit of pipeline logic.

    Implementations declare themselves via the ``aegis.nodes`` entry-point
    group. The assembler chains them into a LangGraph StateGraph in configured
    order.
    """

    name: str

    async def run(self, state: RunState) -> RunStateDelta:
        """Execute node logic against *state*, returning a partial delta.

        The delta is merged into the shared RunState after the call returns.
        Return ``RunStateDelta()`` (all None fields) for a no-op pass-through.
        """
        ...
