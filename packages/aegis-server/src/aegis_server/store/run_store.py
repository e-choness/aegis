"""RunStore — persist run metadata alongside the LangGraph checkpointer (D11/D14).

``InMemoryRunStore`` is used in tests and dev.
``SqliteRunStore`` is the default for ``aegis dev``; requires *aiosqlite*
(installed transitively via langgraph-checkpoint-sqlite).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class RunRecord:
    """Metadata for a single pipeline run."""

    run_id: str
    route: str
    principal_id: str
    status: str  # running | completed | blocked | paused | denied
    approvers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "route": self.route,
            "principal_id": self.principal_id,
            "status": self.status,
            "approvers": self.approvers,
        }


@runtime_checkable
class RunStore(Protocol):
    """Protocol for run metadata persistence."""

    async def create(self, record: RunRecord) -> None: ...
    async def get(self, run_id: str) -> RunRecord | None: ...
    async def update_status(self, run_id: str, status: str) -> None: ...
    async def list_pending(self) -> list[RunRecord]: ...


class InMemoryRunStore:
    """In-memory run store — for tests and dev (no persistence)."""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    async def create(self, record: RunRecord) -> None:
        self._records[record.run_id] = record

    async def get(self, run_id: str) -> RunRecord | None:
        return self._records.get(run_id)

    async def update_status(self, run_id: str, status: str) -> None:
        rec = self._records.get(run_id)
        if rec is not None:
            rec.status = status

    async def list_pending(self) -> list[RunRecord]:
        return [r for r in self._records.values() if r.status == "paused"]


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    route       TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    status      TEXT NOT NULL,
    approvers   TEXT NOT NULL DEFAULT '[]'
)
"""

_INSERT_SQL = (
    "INSERT OR REPLACE INTO runs (run_id, route, principal_id, status, approvers)"
    " VALUES (?, ?, ?, ?, ?)"
)
_SELECT_SQL = "SELECT run_id, route, principal_id, status, approvers FROM runs WHERE run_id = ?"
_UPDATE_SQL = "UPDATE runs SET status = ? WHERE run_id = ?"
_PENDING_SQL = (
    "SELECT run_id, route, principal_id, status, approvers FROM runs WHERE status = 'paused'"
)


def _row_to_record(row: tuple[str, str, str, str, str]) -> RunRecord:
    return RunRecord(
        run_id=row[0],
        route=row[1],
        principal_id=row[2],
        status=row[3],
        approvers=json.loads(row[4]),
    )


class SqliteRunStore:
    """SQLite-backed run store using aiosqlite."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._ready = False

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(_CREATE_SQL)
            await db.commit()
        self._ready = True

    async def create(self, record: RunRecord) -> None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                _INSERT_SQL,
                (record.run_id, record.route, record.principal_id, record.status, json.dumps(record.approvers)),
            )
            await db.commit()

    async def get(self, run_id: str) -> RunRecord | None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(_SELECT_SQL, (run_id,)) as cursor:
                row = await cursor.fetchone()
                return _row_to_record(row) if row is not None else None  # type: ignore[arg-type]

    async def update_status(self, run_id: str, status: str) -> None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(_UPDATE_SQL, (status, run_id))
            await db.commit()

    async def list_pending(self) -> list[RunRecord]:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(_PENDING_SQL) as cursor:
                rows = await cursor.fetchall()
                return [_row_to_record(r) for r in rows]  # type: ignore[arg-type]
