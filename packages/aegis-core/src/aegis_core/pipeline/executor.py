"""PipelineExecutor — manages compiled pipelines (one per route) and runs them."""

from __future__ import annotations

from typing import Any

from aegis_core.pipeline.assembler import CompiledPipeline, PipelineAssembler
from aegis_core.pipeline.protocol import PipelineNode
from aegis_core.pipeline.state import RunState
from aegis_core.providers.protocol import ModelProvider


class PipelineExecutor:
    """Manages a pool of per-route compiled pipelines.

    Pipelines are compiled once via :meth:`register` and reused across
    requests (PROJECT_SPEC D2: "one graph compiled per route at startup;
    recompiled on config reload").
    """

    def __init__(self, checkpointer: Any | None = None) -> None:
        self._pipelines: dict[str, CompiledPipeline] = {}
        self._assembler = PipelineAssembler()
        self._checkpointer = checkpointer

    def register(
        self,
        route: str,
        provider: ModelProvider | None = None,
        ingress: list[PipelineNode] | None = None,
        execute: PipelineNode | None = None,
        egress: list[PipelineNode] | None = None,
        custom_graph: Any | None = None,
    ) -> CompiledPipeline:
        """Compile and cache a pipeline for *route*.

        Returns the compiled pipeline (also accessible via :meth:`get`).
        """
        pipeline = self._assembler.compile(
            ingress=ingress,
            execute=execute,
            egress=egress,
            route=route,
            provider=provider,
            custom_graph=custom_graph,
            checkpointer=self._checkpointer,
        )
        self._pipelines[route] = pipeline
        return pipeline

    def get(self, route: str) -> CompiledPipeline:
        """Return the compiled pipeline for *route*.

        Raises:
            KeyError: If no pipeline has been registered for *route*.
        """
        if route not in self._pipelines:
            raise KeyError(f"No pipeline registered for route '{route}'.")
        return self._pipelines[route]

    async def run(self, route: str, state: RunState) -> RunState:
        """Execute the pipeline for *route* against *state*."""
        return await self.get(route).run(state)

    async def resume(self, run_id: str, route: str, decision: dict[str, object]) -> RunState:
        """Resume a paused run via its route's compiled pipeline."""
        return await self.get(route).resume(run_id, decision)

    def routes(self) -> list[str]:
        """Return all registered route names."""
        return list(self._pipelines.keys())
