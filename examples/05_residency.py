"""Example 05 — Residency enforcement.

Shows how Aegis enforces data-residency constraints: a request destined
for a cross-region provider is rejected by the residency policy.

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


async def run_with_provider(label: str, provider: FakeProvider) -> None:
    assembler = PipelineAssembler()
    pipeline = assembler.compile(provider=provider, route="default")

    state = RunState(
        run_id=str(uuid.uuid4()),
        route="default",
        messages=[Message(role="user", content="Summarise GDPR article 17.")],
        principal="demo-user",
        # Residency constraint: data must stay in the EU.
        metadata={"required_region": "eu-west"},
    )

    result = await pipeline.run(state)
    print(f"[{label}] status={result.status!r}  response={result.response!r}")


async def main() -> None:
    print("--- EU-resident provider (should pass) ---")
    await run_with_provider("eu-west provider", _EUResidentFakeProvider(name="eu-fake"))

    print("\n--- Global provider without residency constraint (passes) ---")
    await run_with_provider("global provider", FakeProvider(name="global-fake"))


if __name__ == "__main__":
    asyncio.run(main())
