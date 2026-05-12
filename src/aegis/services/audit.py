from __future__ import annotations
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from ..models import AuditRecord

logger = logging.getLogger("aegis.audit")


class AuditLogger:
    """
    Writes immutable audit records for every inference call.
    Phase 1: structured JSON to stdout (captured by log aggregator).
    Phase 2: TimescaleDB hot store + S3 Object Lock cold store (7-year retention).
    """

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._lock = threading.Lock()

    def log(self, record: AuditRecord) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record.model_dump(),
        }
        with self._lock:
            self._records.append(entry)
        logger.info(json.dumps(entry))

    def get_records(self, team_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if team_id:
                return [r for r in self._records if r.get("team_id") == team_id]
            return list(self._records)

    def count_restricted_cloud_violations(self) -> int:
        """Compliance invariant: this must always return 0."""
        with self._lock:
            return sum(
                1 for r in self._records
                if r.get("data_classification") == "RESTRICTED" and r.get("tier") == 1
            )
