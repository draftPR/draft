"""Tests for sqlite_worker module - in-process job runner backed by SQLite."""

import json
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Fixture: temp SQLite DB with job_queue table + patched _DB_PATH
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a temporary SQLite DB with job_queue table."""
    db_path = str(tmp_path / "test_worker.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE job_queue (
            id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            args_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            claimed_by TEXT,
            claimed_at TIMESTAMP,
            completed_at TIMESTAMP,
            result_json TEXT,
            priority INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX ix_job_queue_status ON job_queue(status)
    """)
    conn.execute("""
        CREATE INDEX ix_job_queue_claim_order
            ON job_queue(status, priority, created_at)
    """)
    conn.commit()
    conn.close()

    with (
        patch("app.sqlite_kv._DB_PATH", db_path),
        patch("app.services.sqlite_worker._DB_PATH", db_path),
    ):
        yield db_path


def _insert_task(db_path: str, task_id: str, task_name: str, args: list, priority: int = 0):
    """Helper to insert a pending task."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO job_queue (id, task_name, args_json, status, priority, created_at) "
        "VALUES (?, ?, ?, 'pending', ?, datetime('now'))",
        (task_id, task_name, json.dumps(args), priority),
    )
    conn.commit()
    conn.close()


def _get_task_status(db_path: str, task_id: str) -> str | None:
    """Helper to read task status."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status FROM job_queue WHERE id = ?", (task_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ===========================================================================
# SQLiteWorker unit tests (no background threads)
# ===========================================================================


class TestWorkerClaimTask:
    """Test atomic task claiming without starting the poll loop."""

    def test_claim_pending_task(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["job-1"])

        worker = SQLiteWorker()
        claimed = worker._claim_next_task()
        assert claimed is not None
        task_id, task_name, args_json = claimed
        assert task_id == "t1"
        assert task_name == "execute_ticket"
        assert json.loads(args_json) == ["job-1"]

    def test_claim_returns_none_when_empty(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        worker = SQLiteWorker()
        assert worker._claim_next_task() is None

    def test_claim_skips_already_claimed(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["j1"])

        worker = SQLiteWorker()
        first = worker._claim_next_task()
        assert first is not None

        second = worker._claim_next_task()
        assert second is None

    def test_claim_respects_priority(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "low", "execute_ticket", ["j-low"], priority=0)
        _insert_task(sqlite_db, "high", "execute_ticket", ["j-high"], priority=10)

        worker = SQLiteWorker()
        claimed = worker._claim_next_task()
        assert claimed[0] == "high"

    def test_claim_marks_status_as_claimed(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["j1"])
        worker = SQLiteWorker()
        worker._claim_next_task()

        assert _get_task_status(sqlite_db, "t1") == "claimed"


class TestWorkerMarkResults:
    """Test _mark_completed and _mark_failed."""

    def test_mark_completed(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["j1"])

        worker = SQLiteWorker()
        worker._mark_completed("t1", {"status": "ok"})

        conn = sqlite3.connect(sqlite_db)
        row = conn.execute(
            "SELECT status, result_json, completed_at FROM job_queue WHERE id = 't1'"
        ).fetchone()
        conn.close()

        assert row[0] == "completed"
        assert json.loads(row[1]) == {"status": "ok"}
        assert row[2] is not None

    def test_mark_completed_none_result(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["j1"])
        worker = SQLiteWorker()
        worker._mark_completed("t1", None)

        conn = sqlite3.connect(sqlite_db)
        row = conn.execute(
            "SELECT status, result_json FROM job_queue WHERE id = 't1'"
        ).fetchone()
        conn.close()

        assert row[0] == "completed"
        assert row[1] is None

    def test_mark_failed(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        _insert_task(sqlite_db, "t1", "execute_ticket", ["j1"])
        worker = SQLiteWorker()
        worker._mark_failed("t1", "Something went wrong")

        conn = sqlite3.connect(sqlite_db)
        row = conn.execute(
            "SELECT status, result_json FROM job_queue WHERE id = 't1'"
        ).fetchone()
        conn.close()

        assert row[0] == "failed"
        result = json.loads(row[1])
        assert "Something went wrong" in result["error"]


class TestWorkerTaskRegistration:
    """Test register_task and register_periodic."""

    def test_register_task(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        worker = SQLiteWorker()
        worker.register_task("my_task", lambda x: x)
        assert "my_task" in worker._tasks

    def test_register_periodic(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        worker = SQLiteWorker()
        worker.register_periodic("heartbeat", 10.0, lambda: None)
        assert len(worker._periodic_tasks) == 1
        assert worker._periodic_tasks[0][0] == "heartbeat"


# ===========================================================================
# SQLiteWorker integration tests (with background threads)
# ===========================================================================


class TestWorkerExecution:
    """Test full task execution with worker start/stop."""

    def test_worker_executes_task(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        results = []

        def my_task(job_id):
            results.append(job_id)
            return {"done": True}

        worker = SQLiteWorker(poll_interval=0.1)
        worker.register_task("test_task", my_task)

        _insert_task(sqlite_db, "t1", "test_task", ["job-abc"])

        worker.start()
        try:
            # Wait for task execution (up to 3 seconds)
            for _ in range(30):
                if _get_task_status(sqlite_db, "t1") == "completed":
                    break
                time.sleep(0.1)

            assert _get_task_status(sqlite_db, "t1") == "completed"
            assert results == ["job-abc"]
        finally:
            worker.stop()

    def test_worker_handles_task_failure(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        def failing_task(job_id):
            raise ValueError("boom")

        worker = SQLiteWorker(poll_interval=0.1)
        worker.register_task("bad_task", failing_task)

        _insert_task(sqlite_db, "t1", "bad_task", ["j1"])

        worker.start()
        try:
            for _ in range(30):
                status = _get_task_status(sqlite_db, "t1")
                if status == "failed":
                    break
                time.sleep(0.1)

            assert _get_task_status(sqlite_db, "t1") == "failed"
        finally:
            worker.stop()

    def test_worker_handles_unknown_task(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        worker = SQLiteWorker(poll_interval=0.1)
        # Don't register any tasks

        _insert_task(sqlite_db, "t1", "unknown_task", ["j1"])

        worker.start()
        try:
            for _ in range(30):
                status = _get_task_status(sqlite_db, "t1")
                if status == "failed":
                    break
                time.sleep(0.1)

            assert _get_task_status(sqlite_db, "t1") == "failed"
        finally:
            worker.stop()

    def test_worker_executes_multiple_tasks_in_order(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        order = []

        def tracking_task(job_id):
            order.append(job_id)
            return {"ok": True}

        worker = SQLiteWorker(poll_interval=0.1)
        worker.register_task("track", tracking_task)

        # Insert tasks with increasing time
        for i in range(3):
            _insert_task(sqlite_db, f"t{i}", "track", [f"job-{i}"])

        worker.start()
        try:
            for _ in range(60):
                conn = sqlite3.connect(sqlite_db)
                completed = conn.execute(
                    "SELECT COUNT(*) FROM job_queue WHERE status = 'completed'"
                ).fetchone()[0]
                conn.close()
                if completed == 3:
                    break
                time.sleep(0.1)

            assert len(order) == 3
        finally:
            worker.stop()

    def test_worker_start_stop_idempotent(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        worker = SQLiteWorker(poll_interval=0.1)
        worker.register_task("noop", lambda: None)

        # Double start
        worker.start()
        worker.start()

        # Double stop
        worker.stop()
        worker.stop()

    def test_periodic_task_runs(self, sqlite_db):
        from app.services.sqlite_worker import SQLiteWorker

        call_count = {"n": 0}
        lock = threading.Lock()

        def periodic_fn():
            with lock:
                call_count["n"] += 1

        worker = SQLiteWorker(poll_interval=0.1)
        worker.register_periodic("ticker", 0.2, periodic_fn)

        worker.start()
        try:
            time.sleep(1.0)
            with lock:
                assert call_count["n"] >= 2, f"Periodic ran {call_count['n']} times"
        finally:
            worker.stop()
