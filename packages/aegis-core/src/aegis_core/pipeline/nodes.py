"""Built-in pipeline nodes."""

from __future__ import annotations

from aegis_core.pipeline.state import RunState, RunStateDelta
from aegis_core.providers.models import CompletionRequest
from aegis_core.providers.protocol import ModelProvider


class ExecuteNode:
    """Built-in execute-stage node that calls the configured ModelProvider.

    This is the default execute node inserted by the assembler when a
    *provider* argument is supplied but no explicit execute node is given.
    """

    def __init__(self, provider: ModelProvider, name: str = "execute") -> None:
        self.name = name
        self._provider = provider

    async def run(self, state: RunState) -> RunStateDelta:
        req = CompletionRequest(
            messages=state.messages,
            model="",  # provider uses its own configured default
        )
        result = await self._provider.complete(req)
        return RunStateDelta(
            response=result.text,
            usage=result.usage,
            status="completed",
        )
