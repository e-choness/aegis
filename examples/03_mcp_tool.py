"""Example 03 — Governed MCP tool call.

Shows how to configure an Aegis pipeline that inspects MCP tool calls
before they are executed.  Tool calls and results each pass through
dedicated guardrail stages (``tool_call`` and ``tool_result`` in the
pipeline config).

This script runs entirely in-process using a FakeProvider.  For a live
demo with a real MCP server, start ``aegis dev`` and point an MCP client
at ``http://127.0.0.1:8000/mcp``.

Run::

    uv run python examples/03_mcp_tool.py
"""

from __future__ import annotations

import asyncio
import json
import uuid

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message, ToolCall
from aegis_core.testing import FakeProvider


async def main() -> None:
    # FakeProvider returns a tool call on the first completion, then a text
    # answer on the second.  The pipeline MCP node (not activated here for
    # simplicity) would dispatch the call and inject the result.
    tool_call = ToolCall(
        id="call_weather_01",
        name="get_weather",
        arguments={"location": "London", "unit": "celsius"},
    )
    provider = FakeProvider(
        tool_calls_sequence=[[tool_call]],
        complete_response="It is 18 °C and partly cloudy in London.",
    )

    print("[tool_call shape]")
    print(f"  id        : {tool_call.id}")
    print(f"  name      : {tool_call.name}")
    print(f"  arguments : {json.dumps(tool_call.arguments)}")

    info = provider.info()
    print("\n[provider]")
    print(f"  name              : {info.name}")
    print(f"  supports_streaming: {info.supports_streaming}")

    # Simple pipeline run (no MCP execute node; tool loop shown conceptually)
    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content="What is the weather in London?")],
        principal="demo-user",
    )

    result = await pipeline.run(state)

    print("\n[run]")
    print(f"  run_id : {result.run_id}")
    print(f"  status : {result.status}")
    print(f"  events : {len(result.events)}")
    print()
    print("TIP: For a full governed tool loop, add an `mcp:` node to aegis.yaml")
    print("     and point it at an MCP server.  The pipeline will guard tool calls")
    print("     via the `tool_call` and `tool_result` pipeline stages.")


if __name__ == "__main__":
    asyncio.run(main())
