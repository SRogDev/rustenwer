"""FileJobQueue tests (TDD: RED first, then implement).

Contract under test (see docs/plans/phase2.md):
  enqueue(run_id, job_id) -> persists a pending item
  claim() -> atomically takes the oldest-highest-priority item (None when empty)
  remove(run_id) -> drop a queued item
  pending() -> list without removing
  The queue survives process restart (SQLite file).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.training.queue import FileJobQueue


def _ids() -> tuple:
    return uuid4(), uuid4()


def test_enqueue_claim_roundtrip(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    run_id, job_id = _ids()
    q.enqueue(run_id, job_id)
    item = q.claim()
    assert item is not None
    assert item.run_id == run_id
    assert item.job_id == job_id
    assert q.claim() is None  # claimed items are gone


def test_claim_fifo_order(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    first = _ids()
    second = _ids()
    q.enqueue(*first)
    q.enqueue(*second)
    assert q.claim().run_id == first[0]
    assert q.claim().run_id == second[0]


def test_priority_beats_fifo(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    low = _ids()
    high = _ids()
    q.enqueue(*low, priority=0)
    q.enqueue(*high, priority=10)
    assert q.claim().run_id == high[0]


def test_pending_lists_without_removing(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    q.enqueue(*_ids())
    q.enqueue(*_ids())
    assert len(q.pending()) == 2
    assert len(q.pending()) == 2  # still there
    assert len(q) == 2


def test_remove_drops_item(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    run_id, job_id = _ids()
    other = _ids()
    q.enqueue(run_id, job_id)
    q.enqueue(*other)
    assert q.remove(run_id) is True
    assert q.remove(run_id) is False  # already gone
    assert q.claim().run_id == other[0]


def test_queue_survives_reopen(tmp_path: Path) -> None:
    db = tmp_path / "queue.db"
    q1 = FileJobQueue(db)
    run_id, job_id = _ids()
    q1.enqueue(run_id, job_id)
    del q1

    q2 = FileJobQueue(db)  # "process restart"
    assert len(q2.pending()) == 1
    item = q2.claim()
    assert item is not None and item.run_id == run_id


def test_enqueue_same_run_id_replaces(tmp_path: Path) -> None:
    q = FileJobQueue(tmp_path / "queue.db")
    run_id, job_id = _ids()
    q.enqueue(run_id, job_id)
    q.enqueue(run_id, job_id)  # idempotent re-enqueue must not duplicate
    assert len(q.pending()) == 1
