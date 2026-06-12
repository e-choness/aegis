"""McpExecuteNode — execute-stage node with MCP tool-calling support.

Implements the governed tool-call loop (PROJECT_SPEC §2b / D13):

    LLM → [tool-call guard → MCP tool → tool-result guard] → LLM → ...

Each guard position runs in the order supplied.  The first ``block`` verdict
short-circuits; a ``require_approval`` verdict pauses the run using the same
LangGraph interrupt machinery as Step 09 HITL.
"""

from __future__ import annotations

from typing import Any

from aegis_core.mcp.protocol import ToolCallGuard, ToolResultGuard
from aegis_core.mcp.tool_policy import ToolPolicy
from aegis_core.pipeline.state import RunEvent, RunState, RunStateDelta
from aegis_core.providers.models import CompletionRequest, Message, UsageInfo
from aegis_core.providers.protocol import ModelProvider


class McpExecuteNode:
    """Execute-stage PipelineNode with governed MCP tool-calling.

    Place this as the ``execute`` argument to
    :class:`~aegis_core.pipeline.assembler.PipelineAssembler` to enable
    tool-calling with pre/post-call guards.

    Args:
        provider: Model provider used for completions.
        session: Active MCP :class:`~mcp.ClientSession`.  The caller is
            responsible for the session lifecycle.
        tool_call_guards: Guards run *before* each tool invocation.
            Argument scan and exfiltration check.
        tool_result_guards: Guards run *after* each tool invocation.
            Prompt-injection scan.
        tool_policies: Per-tool policy map (tool name → :class:`ToolPolicy`).
        name: Node identifier shown in run events.
        max_iterations: Safety cap on the tool-calling loop.
    """

    def __init__(
        self,
        provider: ModelProvider,
        session: Any,  # mcp.ClientSession — typed as Any to avoid hard import in type hints
        tool_call_guards: list[ToolCallGuard] | None = None,
        tool_result_guards: list[ToolResultGuard] | None = None,
        tool_policies: dict[str, ToolPolicy] | None = None,
        name: str = "mcp_execute",
        max_iterations: int = 10,
    ) -> None:
        self.name = name
        self._provider = provider
        self._session = session
        self._tool_call_guards: list[ToolCallGuard] = tool_call_guards or []
        self._tool_result_guards: list[ToolResultGuard] = tool_result_guards or []
        self._tool_policies: dict[str, ToolPolicy] = tool_policies or {}
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_tools(self) -> list[dict[str, Any]]:
        """Return tool schemas from the MCP session as plain dicts."""
        response = await self._session.list_tools()
        schemas: list[dict[str, Any]] = []
        for tool in response.tools:
            schemas.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                }
            )
        return schemas

    @staticmethod
    def _accumulate(total: UsageInfo, delta: UsageInfo) -> UsageInfo:
        return UsageInfo(
            prompt_tokens=total.prompt_tokens + delta.prompt_tokens,
            completion_tokens=total.completion_tokens + delta.completion_tokens,
            total_tokens=total.total_tokens + delta.total_tokens,
            cost=total.cost + delta.cost,
        )

    # ------------------------------------------------------------------
    # PipelineNode.run()
    # ------------------------------------------------------------------

    async def run(self, state: RunState) -> RunStateDelta:
        """Execute the tool-calling loop and return a :class:`RunStateDelta`."""
        messages: list[Message] = list(state.messages)
        events: list[RunEvent] = []
        total_usage = UsageInfo()

        mcp_tools = await self._list_tools()

        for _iteration in range(self._max_iterations):
            req = CompletionRequest(messages=messages, model="", tools=mcp_tools)
            result = await self._provider.complete(req)
            total_usage = self._accumulate(total_usage, result.usage)

            if not result.tool_calls:
                # No pending tool calls — the model produced a final response.
                return RunStateDelta(
                    response=result.text,
                    usage=total_usage,
                    status="completed",
                    events=events,
                )

            for tool_call in result.tool_calls:
                # ── 1. Tool-call guards (argument scan + exfiltration) ──────
                for guard in self._tool_call_guards:
                    verdict = await guard.scan_call(tool_call.name, tool_call.arguments, state)
                    events.append(
                        RunEvent(
                            stage="mcp_tool_call_guard",
                            node=guard.name,
                            event_type="verdict",
                            data={
                                "verdict": verdict.kind.value,
                                "tool": tool_call.name,
                                "reason": verdict.reason,
                            },
                        )
                    )
                    if verdict.is_block:
                        return RunStateDelta(status="blocked", events=events)
                    if verdict.is_require_approval:
                        return RunStateDelta(status="paused", events=events)

                # ── 2. Per-tool approval policy ─────────────────────────────
                policy = self._tool_policies.get(tool_call.name)
                if policy and policy.require_approval:
                    events.append(
                        RunEvent(
                            stage="mcp_tool_policy",
                            node=f"tool_policy_{tool_call.name}",
                            event_type="verdict",
                            data={
                                "verdict": "require_approval",
                                "tool": tool_call.name,
                                "reason": "per-tool policy requires human approval",
                            },
                        )
                    )
                    return RunStateDelta(status="paused", events=events)

                # ── 3. Call MCP tool ────────────────────────────────────────
                events.append(
                    RunEvent(
                        stage="mcp_tool_call",
                        node=f"mcp_{tool_call.name}",
                        event_type="node_start",
                        data={"tool": tool_call.name, "arguments": tool_call.arguments},
                    )
                )
                call_result = await self._session.call_tool(tool_call.name, tool_call.arguments)
                tool_result_text = "\n".join(
                    block.text
                    for block in call_result.content
                    if hasattr(block, "text")
                )
                events.append(
                    RunEvent(
                        stage="mcp_tool_call",
                        node=f"mcp_{tool_call.name}",
                        event_type="node_end",
                        data={"tool": tool_call.name, "result_length": len(tool_result_text)},
                    )
                )

                # ── 4. Tool-result guards (injection scan) ──────────────────
                for guard in self._tool_result_guards:
                    verdict = await guard.scan_result(tool_call.name, tool_result_text, state)
                    events.append(
                        RunEvent(
                            stage="mcp_tool_result_guard",
                            node=guard.name,
                            event_type="verdict",
                            data={
                                "verdict": verdict.kind.value,
                                "tool": tool_call.name,
                                "reason": verdict.reason,
                            },
                        )
                    )
                    if verdict.is_block:
                        return RunStateDelta(status="blocked", events=events)

                # ── 5. Feed result back into message history ─────────────────
                messages.append(
                    Message(role="tool", content=f"[{tool_call.name}]: {tool_result_text}")
                )

        # Safety: max iterations reached — return whatever text we have.
        return RunStateDelta(
            response="",
            usage=total_usage,
            status="completed",
            events=events,
        )
