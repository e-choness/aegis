"""Aegis pluggy hook specifications."""

from __future__ import annotations

import pluggy

hookspec = pluggy.HookspecMarker("aegis")
hookimpl = pluggy.HookimplMarker("aegis")


class AegisSpec:
    """Hook specifications for the Aegis plugin system.

    Plugins implement these by decorating methods with ``@hookimpl``.
    """

    @hookspec
    def on_run_start(
        self,
        run_id: str,
        route: str,
        principal: str | None,
    ) -> None:
        """Called when a new run begins.

        Args:
            run_id: Unique identifier for this run.
            route: The route name selected for this run.
            principal: The authenticated principal ID, or None if anonymous.
        """

    @hookspec
    def on_node_end(
        self,
        run_id: str,
        node_name: str,
        duration_ms: float,
    ) -> None:
        """Called after each pipeline node completes.

        Args:
            run_id: Unique identifier for this run.
            node_name: The name of the node that just finished.
            duration_ms: Wall-clock time the node took, in milliseconds.
        """

    @hookspec
    def on_verdict(
        self,
        run_id: str,
        node_name: str,
        verdict: str,
    ) -> None:
        """Called when a guardrail emits a verdict.

        Args:
            run_id: Unique identifier for this run.
            node_name: The guardrail node that emitted the verdict.
            verdict: One of ``allow``, ``block``, ``sanitize``, ``require_approval``.
        """

    @hookspec
    def on_run_end(
        self,
        run_id: str,
        status: str,
        usage: dict[str, object],
    ) -> None:
        """Called when a run finishes (success, block, or error).

        Args:
            run_id: Unique identifier for this run.
            status: One of ``ok``, ``blocked``, ``error``, ``pending_approval``.
            usage: Token/cost counters, e.g. ``{"prompt_tokens": 10, ...}``.
        """
