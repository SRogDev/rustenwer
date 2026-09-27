"""Persistent FIFO job queue (Phase 2).

SQLite-backed so queued runs survive an API restart. `claim()` is atomic
(SELECT + DELETE inside one IMMEDIATE transaction): two managers can never
take the same run. A Postgres/Supabase implementation can replace this
later behind the same `JobQueue` interface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class QueuedItem:
    run_id: UUID
    job_id: UUID
    enqueued_at: str
    priority: int = 0


class JobQueue:
    """Queue contract."""

    def enqueue(self, run_id: UUID, job_id: UUID, priority: int = 0) -> None:
        raise NotImplementedError

    def claim(self) -> QueuedItem | None:
        """Atomically take the next item (highest priority, oldest first)."""
        raise NotImplementedError

    def remove(self, run_id: UUID) -> bool:
        """Drop a queued item; True when something was removed."""
        raise NotImplementedError

    def pending(self) -> list[QueuedItem]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    run_id      TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS queue_order_idx ON queue (priority DESC, enqueued_at ASC);
"""


class FileJobQueue(JobQueue):
    """SQLite-backed persistent queue."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, run_id: UUID, job_id: UUID, priority: int = 0) -> None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO queue (run_id, job_id, enqueued_at, priority)"
                " VALUES (?, ?, ?, ?)",
                (str(run_id), str(job_id), now, priority),
            )

    def claim(self) -> QueuedItem | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT run_id, job_id, enqueued_at, priority FROM queue"
                " ORDER BY priority DESC, enqueued_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute("DELETE FROM queue WHERE run_id = ?", (row["run_id"],))
            conn.execute("COMMIT")
            return QueuedItem(
                run_id=UUID(row["run_id"]),
                job_id=UUID(row["job_id"]),
                enqueued_at=row["enqueued_at"],
                priority=row["priority"],
            )

    def remove(self, run_id: UUID) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM queue WHERE run_id = ?", (str(run_id),))
            return cur.rowcount > 0

    def pending(self) -> list[QueuedItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_id, job_id, enqueued_at, priority FROM queue"
                " ORDER BY priority DESC, enqueued_at ASC"
            ).fetchall()
        return [
            QueuedItem(
                run_id=UUID(r["run_id"]),
                job_id=UUID(r["job_id"]),
                enqueued_at=r["enqueued_at"],
                priority=r["priority"],
            )
            for r in rows
        ]

    def __len__(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM queue").fetchone()
            return int(row["n"])
