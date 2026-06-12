"""MCP tool-guard protocols — ToolCallGuard and ToolResultGuard.

These are separate from the main Guardrail protocol: they scan tool call
arguments and tool results rather than message content.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


@runtime_checkable
class ToolCallGuard(Protocol):
    """Guards the tool-call position (argument scan, exfiltration check).

    Implementations inspect the tool name and deserialized arguments before
    the MCP server is invoked.  Return ``Verdict.allow()`` to proceed,
    ``Verdict.block(reason)`` to abort, or ``Verdict.require_approval(prompt)``
    to pause the run pending human review.
    """

    name: str

    async def scan_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: RunState,
    ) -> Verdict:
        """Scan a tool call's arguments before execution."""
        ...


@runtime_checkable
class ToolResultGuard(Protocol):
    """Guards the tool-result position (prompt-injection scan).

    Implementations inspect the stringified tool result after the MCP server
    returns.  Return ``Verdict.allow()`` to pass the result to the model, or
    ``Verdict.block(reason)`` to suppress it (run status → ``"blocked"``).
    """

    name: str

    async def scan_result(
        self,
        tool_name: str,
        result: str,
        state: RunState,
    ) -> Verdict:
        """Scan a tool result after execution."""
        ...
