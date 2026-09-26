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


def _targets(nodes: Iterable[object]) -> Iterator[object]:
    for node in nodes:
        yield node
        # A GuardNode runs guards; they are what loads models.
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
    for target in _targets(nodes):
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
