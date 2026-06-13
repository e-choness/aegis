"""Example 05 — Residency enforcement.

Shows how Aegis surfaces provider residency information so you can build
policies that keep data in the right region.  A ``FakeProvider`` that
claims to be in ``eu-west`` is queried and its ``ProviderInfo.residency``
field is inspected — the same information the residency policy node uses.

Run::

    uv run python examples/05_residency.py
"""

from __future__ import annotations

import asyncio
import uuid

from aegis_core.pipeline import PipelineAssembler, RunState
from aegis_core.providers.models import Message, ProviderInfo, ResidencyInfo
from aegis_core.testing import FakeProvider


class _EUResidentFakeProvider(FakeProvider):
    """FakeProvider pinned to the eu-west region."""

    def info(self) -> ProviderInfo:
        base = super().info()
        return ProviderInfo(
            name=base.name,
            provider_type=base.provider_type,
            models=base.models,
            residency=ResidencyInfo(region="eu-west"),
            supports_streaming=base.supports_streaming,
            supports_embeddings=base.supports_embeddings,
        )


async def run_and_show(label: str, provider: FakeProvider) -> None:
    info = provider.info()
    print(f"\n[{label}]")
    print(f"  provider region : {info.residency.region or 'global (no constraint)'}")

    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content="Summarise GDPR article 17.")],
        principal="demo-user",
        # Label the request with the required region — a residency policy node
        # would compare this against provider.info().residency.region.
        labels={"required_region": "eu-west"},
    )

    result = await pipeline.run(state)
    print(f"  status          : {result.status}")
    print(f"  response        : {result.response!r:.60}")


async def main() -> None:
    print("=== Residency example ===")
    await run_and_show("EU-resident provider", _EUResidentFakeProvider(name="eu-fake"))
    await run_and_show("Global provider (no region)", FakeProvider(name="global-fake"))


if __name__ == "__main__":
    asyncio.run(main())
