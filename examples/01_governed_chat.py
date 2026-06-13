"""Example 01 — Governed chat.

Shows the simplest Aegis usage: send a message through the pipeline and
receive a response.  No real API key is needed — the FakeProvider echoes
the message back so you can run this example immediately.

Run::

    uv run python examples/01_governed_chat.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider


async def main() -> None:
    provider = FakeProvider(complete_response="Hello! How can I help you today?")

    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content="What is Aegis?")],
        principal="demo-user",
    )

    result = await pipeline.run(state)

    print(f"[run_id]  {result.run_id}")
    print(f"[status]  {result.status}")
    print(f"[response]{result.response}")
    print(f"[tokens]  prompt={result.usage.prompt_tokens} "
          f"completion={result.usage.completion_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
