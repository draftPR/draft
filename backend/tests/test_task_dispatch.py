"""Tests for task_dispatch module - unified task enqueue for SQLite/Celery."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from app.services.task_dispatch import TaskHandle, enqueue_task


# ---------------------------------------------------------------------------
# Fixture: temp SQLite DB with job_queue table
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db(tmp_path):
    """Create a temporary SQLite DB with job_queue table."""
    db_path = str(tmp_path / "test_dispatch.db")
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
    conn.commit()
    conn.close()

    with (
        patch("app.sqlite_kv._DB_PATH", db_path),
        patch("app.task_backend._TASK_BACKEND", "sqlite"),
        patch("app.task_backend._SMART_KANBAN_MODE", ""),
    ):
        yield db_path


# ===========================================================================
# TaskHandle tests
# ===========================================================================


class TestTaskHandle:
    def test_has_id_attribute(self):
        handle = TaskHandle("abc-123")
        assert handle.id == "abc-123"


# ===========================================================================
# SQLite enqueue tests
# ===========================================================================


class TestEnqueueSQLite:
    def test_enqueue_inserts_row(self, sqlite_db):
        handle = enqueue_task("execute_ticket", args=["job-1"])
        assert handle.id is not None

        conn = sqlite3.connect(sqlite_db)
        row = conn.execute(
            "SELECT task_name, args_json, status FROM job_queue WHERE id = ?",
            (handle.id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "execute_ticket"
        assert json.loads(row[1]) == ["job-1"]
        assert row[2] == "pending"

    def test_enqueue_default_args(self, sqlite_db):
        handle = enqueue_task("verify_ticket")

        conn = sqlite3.connect(sqlite_db)
        row = conn.execute(
            "SELECT args_json FROM job_queue WHERE id = ?",
            (handle.id,),
        ).fetchone()
        conn.close()

        assert json.loads(row[0]) == []

    def test_enqueue_returns_unique_ids(self, sqlite_db):
        h1 = enqueue_task("execute_ticket", args=["j1"])
        h2 = enqueue_task("execute_ticket", args=["j2"])
        assert h1.id != h2.id

    def test_enqueue_multiple_tasks(self, sqlite_db):
        for i in range(5):
            enqueue_task("execute_ticket", args=[f"job-{i}"])

        conn = sqlite3.connect(sqlite_db)
        count = conn.execute("SELECT COUNT(*) FROM job_queue").fetchone()[0]
        conn.close()
        assert count == 5


# ===========================================================================
# Celery enqueue tests
# ===========================================================================


class TestEnqueueCelery:
    def test_enqueue_delegates_to_celery(self):
        mock_result = MagicMock()
        mock_result.id = "celery-task-id"

        mock_celery = MagicMock()
        mock_celery.send_task.return_value = mock_result

        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.celery_app.celery_app", mock_celery),
        ):
            handle = enqueue_task("execute_ticket", args=["job-1"])

        assert handle.id == "celery-task-id"
        mock_celery.send_task.assert_called_once_with(
            "execute_ticket", args=["job-1"]
        )


# ===========================================================================
# Backend routing tests
# ===========================================================================


class TestBackendRouting:
    def test_sqlite_backend_routes_to_sqlite(self, sqlite_db):
        with patch("app.services.task_dispatch._enqueue_sqlite") as mock_sq:
            mock_sq.return_value = TaskHandle("sq-id")
            handle = enqueue_task("execute_ticket", args=["j1"])
            mock_sq.assert_called_once_with("execute_ticket", ["j1"])
            assert handle.id == "sq-id"

    def test_redis_backend_routes_to_celery(self):
        with (
            patch("app.task_backend._TASK_BACKEND", "redis"),
            patch("app.task_backend._SMART_KANBAN_MODE", ""),
            patch("app.services.task_dispatch._enqueue_celery") as mock_cel,
        ):
            mock_cel.return_value = TaskHandle("cel-id")
            handle = enqueue_task("verify_ticket", args=["j2"])
            mock_cel.assert_called_once_with("verify_ticket", ["j2"])
            assert handle.id == "cel-id"
