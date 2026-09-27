"""PipelineExecutor — manages compiled pipelines (one per route) and runs them."""

from __future__ import annotations

from typing import Any

from aegis_core.pipeline.assembler import CompiledPipeline, PipelineAssembler
from aegis_core.pipeline.protocol import PipelineNode
from aegis_core.pipeline.state import RunState
from aegis_core.pipeline.warmup import nodes_and_guards, warm_up
from aegis_core.providers.protocol import ModelProvider


class PipelineExecutor:
    """Manages a pool of per-route compiled pipelines.

    Pipelines are compiled once via :meth:`register` and reused across
    requests (PROJECT_SPEC D2: "one graph compiled per route at startup;
    recompiled on config reload").
    """

    def __init__(self, checkpointer: Any | None = None) -> None:
        self._pipelines: dict[str, CompiledPipeline] = {}
        self._nodes: dict[str, list[PipelineNode]] = {}
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
        self._nodes[route] = [*(ingress or []), *([execute] if execute else []), *(egress or [])]
        return pipeline

    async def warmup(self) -> list[str]:
        """Warm every registered route's nodes (see :mod:`aegis_core.pipeline.warmup`)."""
        return await warm_up(node for nodes in self._nodes.values() for node in nodes)

    def reset_usage(self, route: str, principal: str) -> int:
        """Clear *principal*'s accumulated usage (e.g. a spend cap) on *route*.

        Calls the optional, duck-typed ``reset_usage(principal)`` on each of the
        route's nodes and the guards inside them. Returns how many were reset.
        """
        seen: set[int] = set()
        for target in nodes_and_guards(self._nodes.get(route, [])):
            reset = getattr(target, "reset_usage", None)
            if callable(reset) and id(target) not in seen:
                seen.add(id(target))
                reset(principal)
        return len(seen)

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
