"""Built-in MCP tool guards.

``ExfiltrationGuard`` — tool-call guard that blocks arguments containing
PII mask placeholders (prevents leaking masked data to external MCP tools).

``ToolResultInjectionGuard`` — tool-result guard that blocks results
containing common prompt-injection patterns.
"""

from __future__ import annotations

import json
from typing import Any

from aegis_core.mcp.protocol import ToolCallGuard, ToolResultGuard
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.verdict import Verdict


class ExfiltrationGuard:
    """Blocks tool calls whose arguments contain PII mask placeholders.

    When the PII pack is active the mask_map channel holds a mapping from
    placeholder tokens (e.g. ``"<PERSON_0>"``) to original values.  If any
    tool-call argument serialises to a string that contains a placeholder, the
    call is blocked — the model is attempting to forward masked PII to an
    external system.
    """

    name = "mcp_exfiltration_guard"

    async def scan_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: RunState,
    ) -> Verdict:
        if not state.mask_map:
            return Verdict.allow()

        try:
            arg_text = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            arg_text = str(arguments)

        for placeholder in state.mask_map.values():
            if placeholder and placeholder in arg_text:
                return Verdict.block(
                    f"tool '{tool_name}' arguments contain PII mask placeholder {placeholder!r}; "
                    "masked data must not be forwarded to external tools"
                )
        return Verdict.allow()


# Assertion: ExfiltrationGuard satisfies ToolCallGuard protocol.
assert isinstance(ExfiltrationGuard(), ToolCallGuard)


class ToolResultInjectionGuard:
    """Blocks tool results that contain prompt-injection patterns.

    Checks for common instruction-hijack phrases in the tool's output string.
    This is a lightweight fast-path guard; pair with LLM Guard for
    model-assisted detection.
    """

    name = "mcp_result_injection_guard"

    # Lowercase substrings that signal an injection attempt.
    _PATTERNS: tuple[str, ...] = (
        "ignore previous",
        "ignore all previous",
        "disregard",
        "you are now",
        "new instructions:",
        "system prompt",
        "forget your instructions",
    )

    async def scan_result(
        self,
        tool_name: str,
        result: str,
        state: RunState,
    ) -> Verdict:
        lower = result.lower()
        for pattern in self._PATTERNS:
            if pattern in lower:
                return Verdict.block(
                    f"tool result from '{tool_name}' contains potential injection pattern {pattern!r}"
                )
        return Verdict.allow()


# Assertion: ToolResultInjectionGuard satisfies ToolResultGuard protocol.
assert isinstance(ToolResultInjectionGuard(), ToolResultGuard)
