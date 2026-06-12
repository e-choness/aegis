"""Guardrail Protocol — the public contract for all guardrail implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


@runtime_checkable
class Guardrail(Protocol):
    """A single guardrail that scans content and returns a Verdict.

    Implementations register themselves under the ``aegis.guardrails``
    entry-point group.  The verdict spine chains them in configured order.
    """

    name: str

    async def scan(self, state: RunState) -> Verdict:
        """Scan the request/response state and return a Verdict.

        Must not call any external model provider.  For guards that wrap
        a model (e.g. LLM Guard), stub or mock the provider in tests.
        """
        ...
