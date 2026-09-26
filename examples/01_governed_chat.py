"""Example 01 — Governed chat: the model never sees the PII.

Builds a route with the PII pack (the same `aegis.pii` pack `aegis.yaml`
uses), sends a message containing an email address and a phone number, and
shows three things: what the user sent, what the model actually received, and
what the user got back.

Run::

    docker compose run --rm dev uv run python examples/01_governed_chat.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_pack_pii.factory import from_config as pii_pack

from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider


async def main() -> None:
    # A mock model that refers back to the (masked) email address it was given.
    provider = FakeProvider(complete_response="Done — I'll send the summary to <EMAIL_ADDRESS_0>.")

    pii = pii_pack("pii", GuardrailConfig(pack="aegis.pii", mode="mask"))
    pipeline = PipelineAssembler().compile(
        ingress=pii["ingress"], egress=pii["egress"], provider=provider, route="default"
    )

    user_text = "Please send the summary to jane.doe@example.com or call 416-555-0199."
    result = await pipeline.run(
        RunState(
            run_id=str(uuid.uuid4()),
            route="default",
            messages=[Message(role="user", content=user_text)],
            principal="demo-user",
        )
    )

    print(f"user sent      : {user_text}")
    print(f"model received : {provider.complete_calls[0].messages[-1].content}")
    print(f"user got back  : {result.response}")
    print(f"status         : {result.status}")


if __name__ == "__main__":
    asyncio.run(main())
