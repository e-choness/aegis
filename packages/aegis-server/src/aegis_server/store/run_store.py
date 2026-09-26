"""RunStore — persist run metadata alongside the LangGraph checkpointer (D11/D14).

``InMemoryRunStore`` is used in tests and dev.
``SqliteRunStore`` persists runs to SQLite; requires *aiosqlite*
(installed transitively via langgraph-checkpoint-sqlite).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass
class RunRecord:
    """Metadata for a single pipeline run."""

    run_id: str
    route: str
    principal_id: str
    status: str  # running | completed | blocked | paused | denied | pending
    approvers: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    events: list[dict[str, object]] = field(default_factory=list)
    config_digest: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "route": self.route,
            "principal_id": self.principal_id,
            "status": self.status,
            "approvers": self.approvers,
            "created_at": self.created_at,
            "events": self.events,
            "config_digest": self.config_digest,
        }


@runtime_checkable
class RunStore(Protocol):
    """Protocol for run metadata persistence."""

    async def create(self, record: RunRecord) -> None: ...
    async def get(self, run_id: str) -> RunRecord | None: ...
    async def update_status(self, run_id: str, status: str) -> None: ...
    async def update_events(
        self,
        run_id: str,
        events: list[dict[str, object]],
        config_digest: str | None,
    ) -> None: ...
    async def list_pending(self) -> list[RunRecord]: ...
    async def list_runs(
        self,
        principal: str | None = None,
        route: str | None = None,
        since: str | None = None,
    ) -> list[RunRecord]: ...


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

    async def update_events(
        self,
        run_id: str,
        events: list[dict[str, object]],
        config_digest: str | None,
    ) -> None:
        rec = self._records.get(run_id)
        if rec is not None:
            rec.events = events
            rec.config_digest = config_digest

    async def list_pending(self) -> list[RunRecord]:
        return [r for r in self._records.values() if r.status == "paused"]

    async def list_runs(
        self,
        principal: str | None = None,
        route: str | None = None,
        since: str | None = None,
    ) -> list[RunRecord]:
        records = list(self._records.values())
        if principal is not None:
            records = [r for r in records if r.principal_id == principal]
        if route is not None:
            records = [r for r in records if r.route == route]
        if since is not None:
            records = [r for r in records if r.created_at >= since]
        return records


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    route        TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    status       TEXT NOT NULL,
    approvers    TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL DEFAULT '',
    events       TEXT NOT NULL DEFAULT '[]',
    config_digest TEXT
)
"""

_MIGRATE_EVENTS_SQL = "ALTER TABLE runs ADD COLUMN events TEXT NOT NULL DEFAULT '[]'"
_MIGRATE_DIGEST_SQL = "ALTER TABLE runs ADD COLUMN config_digest TEXT"

_INSERT_SQL = (
    "INSERT OR REPLACE INTO runs"
    " (run_id, route, principal_id, status, approvers, created_at, events, config_digest)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_SQL = (
    "SELECT run_id, route, principal_id, status, approvers, created_at, events, config_digest"
    " FROM runs WHERE run_id = ?"
)
_UPDATE_SQL = "UPDATE runs SET status = ? WHERE run_id = ?"
_UPDATE_EVENTS_SQL = (
    "UPDATE runs SET events = ?, config_digest = ? WHERE run_id = ?"
)
_PENDING_SQL = (
    "SELECT run_id, route, principal_id, status, approvers, created_at, events, config_digest"
    " FROM runs WHERE status = 'paused'"
)
_LIST_SQL = (
    "SELECT run_id, route, principal_id, status, approvers, created_at, events, config_digest"
    " FROM runs"
)


def _row_to_record(row: tuple[str, ...]) -> RunRecord:
    return RunRecord(
        run_id=row[0],
        route=row[1],
        principal_id=row[2],
        status=row[3],
        approvers=json.loads(row[4]),
        created_at=row[5],
        events=json.loads(row[6]) if len(row) > 6 and row[6] else [],
        config_digest=row[7] if len(row) > 7 else None,
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
            # Idempotent migrations for existing databases without the new columns.
            for migrate_sql in (_MIGRATE_EVENTS_SQL, _MIGRATE_DIGEST_SQL):
                try:
                    await db.execute(migrate_sql)
                except Exception:
                    pass
            await db.commit()
        self._ready = True

    async def create(self, record: RunRecord) -> None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                _INSERT_SQL,
                (
                    record.run_id,
                    record.route,
                    record.principal_id,
                    record.status,
                    json.dumps(record.approvers),
                    record.created_at,
                    json.dumps(record.events),
                    record.config_digest,
                ),
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

    async def update_events(
        self,
        run_id: str,
        events: list[dict[str, object]],
        config_digest: str | None,
    ) -> None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(_UPDATE_EVENTS_SQL, (json.dumps(events), config_digest, run_id))
            await db.commit()

    async def list_pending(self) -> list[RunRecord]:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(_PENDING_SQL) as cursor:
                rows = await cursor.fetchall()
                return [_row_to_record(r) for r in rows]  # type: ignore[arg-type]

    async def list_runs(
        self,
        principal: str | None = None,
        route: str | None = None,
        since: str | None = None,
    ) -> list[RunRecord]:
        await self._ensure_table()
        import aiosqlite

        sql = _LIST_SQL
        params: list[str] = []
        clauses: list[str] = []
        if principal is not None:
            clauses.append("principal_id = ?")
            params.append(principal)
        if route is not None:
            clauses.append("route = ?")
            params.append(route)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [_row_to_record(r) for r in rows]  # type: ignore[arg-type]
