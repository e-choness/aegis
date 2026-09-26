"""Example 05 — Residency: fail-closed, or pause for a human.

The same request goes to three routes whose endpoints are in different
regions, all governed by the `aegis.residency` pack with Canada as the only
allowed region:

* ``ca``        — endpoint in ca-central-1 → allowed
* ``us_strict`` — endpoint in us-east-1, block mode → blocked, provider never called
* ``us_review`` — endpoint in us-east-1, ``require_approval: true`` → paused for review

Run::

    docker compose run --rm dev uv run python examples/05_residency.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_pack_residency.factory import from_config as residency_pack

from aegis_core.packs import GuardrailConfig
from aegis_core.pipeline import PipelineExecutor, RunState
from aegis_core.pipeline.checkpointer import make_memory_checkpointer
from aegis_core.providers.models import Message
from aegis_core.testing import FakeProvider

ROUTES = {
    #  route        endpoint region  pause instead of block?
    "ca": ("ca-central-1", False),
    "us_strict": ("us-east-1", False),
    "us_review": ("us-east-1", True),
}


async def main() -> None:
    executor = PipelineExecutor(checkpointer=make_memory_checkpointer())
    providers: dict[str, FakeProvider] = {}
    for route, (region, pause) in ROUTES.items():
        cfg = GuardrailConfig.model_validate(
            {
                "pack": "aegis.residency",
                "region": region,
                "jurisdiction": region.split("-")[0].upper(),
                "allowed_regions": ["ca-central-1"],
                "require_approval": pause,
            }
        )
        providers[route] = FakeProvider(complete_response=f"answered from {region}")
        executor.register(route, provider=providers[route], ingress=residency_pack(route, cfg)["ingress"])

    for route in ROUTES:
        result = await executor.run(
            route,
            RunState(
                run_id=str(uuid.uuid4()),
                route=route,
                messages=[Message(role="user", content="Assess this Canadian applicant")],
            ),
        )
        verdict = next(e.data for e in result.events if e.event_type == "verdict")
        called = "yes" if providers[route].complete_calls else "no"
        print(f"{route:<10} status={result.status:<9} verdict={verdict['verdict']:<17} provider called: {called}")
        if verdict.get("reason"):
            print(f"{'':<10} reason: {verdict['reason']}")


if __name__ == "__main__":
    asyncio.run(main())
