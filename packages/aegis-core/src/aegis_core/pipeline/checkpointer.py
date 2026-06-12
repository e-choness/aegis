"""Checkpointer factory helpers (PROJECT_SPEC D11).

The only module in aegis-core that imports langgraph checkpointer packages.
"""

from __future__ import annotations

from typing import Any


def make_memory_checkpointer() -> Any:
    """Return an in-memory MemorySaver (no persistence — for tests / dev)."""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def sqlite_checkpointer(path: str) -> Any:
    """Return an async context-manager yielding an ``AsyncSqliteSaver``.

    Usage::

        async with sqlite_checkpointer(path) as cp:
            executor = PipelineExecutor(checkpointer=cp)
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    return AsyncSqliteSaver.from_conn_string(path)


def postgres_checkpointer(conn_string: str) -> Any:
    """Return an async context-manager yielding an ``AsyncPostgresSaver``.

    Usage::

        async with postgres_checkpointer(conn_string) as cp:
            executor = PipelineExecutor(checkpointer=cp)
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    return AsyncPostgresSaver.from_conn_string(conn_string)
