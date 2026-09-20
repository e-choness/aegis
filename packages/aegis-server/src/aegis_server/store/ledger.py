"""Evidence ledger — append-only, hash-chained record store (Phase 2).

Two record types emitted into the same ``evidence`` table:

* ``model_inventory`` — one per (route, config digest), emitted on server start.
* ``run_evidence`` — one per completed/blocked/denied run.

Hash chain: ``hash = sha256(canonical_json(record_without_hash_field))``.
The ``prev_hash`` field is *included* in the canonical JSON, so each record
commits to the full chain up to that point.  Genesis ``prev_hash`` is the
literal string ``"genesis"``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def compute_hash(record_without_hash: dict) -> str:
    """Return ``sha256:<hex>`` over the canonical JSON of *record_without_hash*."""
    return "sha256:" + hashlib.sha256(_canonical(record_without_hash).encode()).hexdigest()


def redact_events(events: list[dict]) -> list[dict]:
    """Strip ``mask_map`` and raw ``messages`` values from event data before ledger storage.

    The PII mask node records entity *types* and *counts* only; the actual
    mask map (token↔replacement pairs) must never enter the ledger.
    """
    out: list[dict] = []
    for ev in events:
        ev2 = dict(ev)
        data = ev2.get("data")
        if isinstance(data, dict):
            ev2["data"] = {k: v for k, v in data.items() if k not in ("mask_map", "messages")}
        out.append(ev2)
    return out


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def make_inventory_record(
    route: str,
    config_digest: str | None,
    route_meta: dict,
    config_path: str | None,
    deployed_at: str | None = None,
) -> dict:
    """Return an ``model_inventory`` body (no hash/seq — appended by the store)."""
    from datetime import date, timedelta

    deployed = deployed_at or _now_iso()
    review_days = route_meta.get("review_interval_days")
    next_review: str | None = None
    if review_days is not None:
        try:
            d = date.fromisoformat(deployed[:10])
            next_review = (d + timedelta(days=int(review_days))).isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "record_type": "model_inventory",
        "model_id": route,
        "model_name": route,
        "model_description": route_meta.get("description", f"route {route}"),
        "model_risk_rating": route_meta.get("risk_rating"),
        "model_owner": route_meta.get("owner"),
        "model_developer": "aegis-gateway 2.0.0a0",
        "model_origin": "vendor",
        "model_version": config_digest,
        "date_of_deployment": deployed,
        "model_dependencies": [],
        "data_sources": ["ingress messages"],
        "approved_uses": {},
        "model_limitations": [],
        "monitoring_status": "active",
        "date_of_most_recent_review": None,
        "next_review_date": next_review,
        "aegis_config_path": config_path,
    }


def make_run_evidence(
    record: object,
    completed_at: str,
    approver: dict | None = None,
) -> dict:
    """Return a ``run_evidence`` body from a RunRecord-like object.

    Uses ``getattr`` so this module does not import from ``run_store``
    (avoids circular imports). *approver* carries ``{"principal_id",
    "decision", "at"}`` when this record reflects a HITL resume decision.
    """
    return {
        "record_type": "run_evidence",
        "run_id": getattr(record, "run_id", ""),
        "model_id": getattr(record, "route", ""),
        "model_version": getattr(record, "config_digest", None),
        "principal_id": getattr(record, "principal_id", ""),
        "created_at": getattr(record, "created_at", ""),
        "completed_at": completed_at,
        "status": getattr(record, "status", ""),
        "events": redact_events(list(getattr(record, "events", []))),
        "approver": approver,
    }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LedgerStore(Protocol):
    """Append-only hash-chained evidence store."""

    async def append(self, run_id: str | None, body: dict) -> dict:
        """Append *body* as a new record; return the full stored record (with seq/hash)."""
        ...

    async def list_records(
        self,
        since_seq: int = 0,
        route: str | None = None,
    ) -> list[dict]:
        """Return records with ``seq > since_seq``, optionally filtered by ``model_id``."""
        ...

    async def get_head(self) -> dict | None:
        """Return the most recently appended record, or ``None`` if empty."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (tests / dev)
# ---------------------------------------------------------------------------


class InMemoryLedgerStore:
    """Volatile in-memory ledger — for tests and dev."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    async def append(self, run_id: str | None, body: dict) -> dict:
        seq = len(self._records) + 1
        prev_hash = self._records[-1]["hash"] if self._records else "genesis"
        record: dict = {"seq": seq, "prev_hash": prev_hash, **body}
        record["hash"] = compute_hash({k: v for k, v in record.items() if k != "hash"})
        self._records.append(record)
        return record

    async def list_records(self, since_seq: int = 0, route: str | None = None) -> list[dict]:
        out = [r for r in self._records if r["seq"] > since_seq]
        if route is not None:
            out = [r for r in out if r.get("model_id") == route]
        return out

    async def get_head(self) -> dict | None:
        return self._records[-1] if self._records else None


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS evidence (
    seq       INTEGER PRIMARY KEY,
    run_id    TEXT,
    record    TEXT NOT NULL,
    hash      TEXT NOT NULL,
    prev_hash TEXT NOT NULL
)
"""

# Append-only triggers — prevent UPDATE and DELETE at the SQL layer.
_TRIGGER_NO_UPDATE = """
CREATE TRIGGER IF NOT EXISTS evidence_no_update BEFORE UPDATE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence ledger is append-only'); END
"""

_TRIGGER_NO_DELETE = """
CREATE TRIGGER IF NOT EXISTS evidence_no_delete BEFORE DELETE ON evidence
BEGIN SELECT RAISE(ABORT, 'evidence ledger is append-only'); END
"""


class SqliteLedgerStore:
    """SQLite-backed append-only evidence ledger (requires *aiosqlite*)."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._ready = False

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            await db.execute(_CREATE_SQL)
            await db.execute(_TRIGGER_NO_UPDATE)
            await db.execute(_TRIGGER_NO_DELETE)
            await db.commit()
        self._ready = True

    async def append(self, run_id: str | None, body: dict) -> dict:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            # Determine next seq and prev_hash atomically within one connection.
            async with db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM evidence") as cur:
                next_seq: int = (await cur.fetchone())[0]  # type: ignore[index]
            async with db.execute(
                "SELECT hash FROM evidence ORDER BY seq DESC LIMIT 1"
            ) as cur:
                head = await cur.fetchone()
            prev_hash: str = head[0] if head else "genesis"  # type: ignore[index]

            record: dict = {"seq": next_seq, "prev_hash": prev_hash, **body}
            record["hash"] = compute_hash({k: v for k, v in record.items() if k != "hash"})

            await db.execute(
                "INSERT INTO evidence (seq, run_id, record, hash, prev_hash)"
                " VALUES (?, ?, ?, ?, ?)",
                (next_seq, run_id, json.dumps(record), record["hash"], prev_hash),
            )
            await db.commit()
        return record

    async def list_records(self, since_seq: int = 0, route: str | None = None) -> list[dict]:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT record FROM evidence WHERE seq > ? ORDER BY seq",
                (since_seq,),
            ) as cur:
                rows = await cur.fetchall()

        records = [json.loads(row[0]) for row in rows]
        if route is not None:
            records = [r for r in records if r.get("model_id") == route]
        return records

    async def get_head(self) -> dict | None:
        await self._ensure_table()
        import aiosqlite

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT record FROM evidence ORDER BY seq DESC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row[0]) if row else None
