"""GuardrailContractKit — shipped with aegis-core for plug-in authors to verify their guard."""

from __future__ import annotations

from aegis_core.guardrails.protocol import Guardrail
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict
from aegis_core.providers.models import Message


def _make_state(content: str) -> RunState:
    return RunState(
        run_id="contract-test",
        route="default",
        messages=[Message(role="user", content=content)],
    )


class GuardrailContractKit:
    """Asserts the full Guardrail contract against a guardrail instance.

    Usage in pytest::

        kit = GuardrailContractKit(MyGuard())
        kit.assert_all()

    Or individually::

        kit.assert_isinstance()
        kit.assert_name()
        asyncio.run(kit.assert_scan_returns_verdict())
        asyncio.run(kit.assert_blocks("bad content"))
        asyncio.run(kit.assert_allows("good content"))
    """

    def __init__(self, guard: object) -> None:
        self._guard = guard

    # ------------------------------------------------------------------
    # Individual assertions
    # ------------------------------------------------------------------

    def assert_isinstance(self) -> None:
        """Guard satisfies the Guardrail runtime-checkable Protocol."""
        assert isinstance(self._guard, Guardrail), (
            f"{type(self._guard).__name__} does not satisfy Guardrail Protocol"
        )

    def assert_name(self) -> None:
        """Guard has a non-empty string ``name`` attribute."""
        name = getattr(self._guard, "name", None)
        assert isinstance(name, str), "Guardrail.name must be a string"
        assert name, "Guardrail.name must be non-empty"

    async def assert_scan_returns_verdict(self) -> None:
        """scan() returns a Verdict instance."""
        state = _make_state("test content")
        result = await self._guard.scan(state)  # type: ignore[union-attr]
        assert isinstance(result, Verdict), "scan() must return a Verdict"

    async def assert_blocks(self, bad_content: str) -> None:
        """scan() returns a block Verdict for *bad_content*."""
        state = _make_state(bad_content)
        result = await self._guard.scan(state)  # type: ignore[union-attr]
        assert result.is_block, (
            f"Expected block verdict for content {bad_content!r}, got {result.kind!r}"
        )

    async def assert_allows(self, good_content: str) -> None:
        """scan() returns an allow Verdict for *good_content*."""
        state = _make_state(good_content)
        result = await self._guard.scan(state)  # type: ignore[union-attr]
        assert result.is_allow, (
            f"Expected allow verdict for content {good_content!r}, got {result.kind!r}"
        )

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
        await self.assert_scan_returns_verdict()
