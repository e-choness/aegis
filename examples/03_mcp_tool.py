"""Example 03 — Governed MCP tool call.

Shows how Aegis wraps MCP tool calls so every tool invocation passes
through the guardrail pipeline before being handed to the model.

This example uses the in-process SDK (no server needed) with a stub
MCP client that simulates a tool returning results.

Run::

    uv run python examples/03_mcp_tool.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message, ToolCall
from aegis_core.testing import FakeProvider


async def main() -> None:
    # Build a FakeProvider that first returns a tool call, then a final response.
    tool_call = ToolCall(
        id="call_01",
        name="get_weather",
        arguments={"location": "London"},
    )
    provider = FakeProvider(
        tool_calls_sequence=[[tool_call]],   # first response: call the tool
        complete_response="It is 18 °C and partly cloudy in London.",
    )

    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content="What's the weather in London?")],
        principal="demo-user",
    )

    result = await pipeline.run(state)

    print(f"[run_id]   {result.run_id}")
    print(f"[status]   {result.status}")
    print(f"[response] {result.response}")

    tool_events = [e for e in result.events if "tool" in e.type.lower()]
    print(f"[events]   {len(result.events)} total, {len(tool_events)} tool-related")


if __name__ == "__main__":
    asyncio.run(main())
