"""NodeContractKit — shipped with aegis-core for plug-in authors to verify their PipelineNode."""

from __future__ import annotations

from aegis_core.pipeline.protocol import PipelineNode
from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.providers.models import Message


def _make_state(content: str) -> RunState:
    return RunState(
        run_id="contract-test",
        route="default",
        messages=[Message(role="user", content=content)],
    )


class NodeContractKit:
    """Asserts the full PipelineNode contract against a node instance.

    Usage in pytest::

        kit = NodeContractKit(MyNode())
        kit.assert_all()

    Or individually::

        kit.assert_isinstance()
        kit.assert_name()
        asyncio.run(kit.assert_run_returns_delta())
    """

    def __init__(self, node: object) -> None:
        self._node = node

    # ------------------------------------------------------------------
    # Individual assertions
    # ------------------------------------------------------------------

    def assert_isinstance(self) -> None:
        """Node satisfies the PipelineNode runtime-checkable Protocol."""
        assert isinstance(self._node, PipelineNode), (
            f"{type(self._node).__name__} does not satisfy PipelineNode Protocol"
        )

    def assert_name(self) -> None:
        """Node has a non-empty string ``name`` attribute."""
        name = getattr(self._node, "name", None)
        assert isinstance(name, str), "PipelineNode.name must be a string"
        assert name, "PipelineNode.name must be non-empty"

    async def assert_run_returns_delta(self) -> None:
        """run() returns a RunStateDelta instance."""
        state = _make_state("test content")
        result = await self._node.run(state)  # type: ignore[union-attr]
        assert isinstance(result, RunStateDelta), "run() must return a RunStateDelta"

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def assert_all(self) -> None:
        """Run all synchronous contract assertions."""
        self.assert_isinstance()
        self.assert_name()

    async def assert_all_async(self) -> None:
        """Run all contract assertions including async ones."""
        self.assert_all()
        await self.assert_run_returns_delta()
