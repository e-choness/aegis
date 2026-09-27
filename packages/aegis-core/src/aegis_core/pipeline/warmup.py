"""Warm-up — load models at startup instead of on the first request.

A node or guard that loads something expensive (a spaCy pipeline, a
transformer) may define ``warmup()``; it is optional and duck-typed, so
existing plugins need no change. The server calls :func:`warm_up` once in the
background after startup and reports progress on ``/v1/health``.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Iterable, Iterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Warmable(Protocol):
    """Anything with a ``warmup()`` method (sync or async)."""

    def warmup(self) -> Any:
        """Load whatever the first request would otherwise wait for."""
        ...


def nodes_and_guards(nodes: Iterable[object]) -> Iterator[object]:
    """Each node, followed by the guards inside it if it is a GuardNode.

    Optional hooks (``warmup()``, ``reset_usage()``) usually live on guards —
    they hold the models and ledgers — not on the GuardNode that runs them.
    """
    for node in nodes:
        yield node
        yield from getattr(node, "guards", None) or ()


async def warm_up(nodes: Iterable[object]) -> list[str]:
    """Call ``warmup()`` once on every node — and every guard inside one — that has it.

    Shared objects (the same detector on several routes) are warmed once.
    Synchronous warm-ups run in a worker thread so the event loop keeps
    serving requests. Returns the names of what was warmed; exceptions
    propagate so the caller can report a failed warm-up.
    """
    seen: set[int] = set()
    warmed: list[str] = []
    for target in nodes_and_guards(nodes):
        method = getattr(target, "warmup", None)
        if not callable(method) or id(target) in seen:
            continue
        seen.add(id(target))
        if inspect.iscoroutinefunction(method):
            await method()
        else:
            await asyncio.to_thread(method)
        warmed.append(str(getattr(target, "name", type(target).__name__)))
    return warmed
