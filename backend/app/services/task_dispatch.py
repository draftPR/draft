"""Unified task dispatch for both Celery and SQLite backends.

Replaces direct celery_app.send_task() / .delay() calls throughout the codebase.
"""

import json
import logging
import time
import uuid

from app.task_backend import is_sqlite_backend

logger = logging.getLogger(__name__)


class TaskHandle:
    """Opaque handle returned by enqueue_task.

    Compatible with Celery's AsyncResult interface (has .id attribute).
    """

    def __init__(self, task_id: str):
        self.id = task_id


def enqueue_task(task_name: str, args: list | None = None) -> TaskHandle:
    """Enqueue a task via SQLite or Celery based on TASK_BACKEND.

    Args:
        task_name: The task name (e.g., "execute_ticket", "verify_ticket")
        args: Positional arguments for the task

    Returns:
        TaskHandle with .id attribute (task ID string)
    """
    args = args or []

    if is_sqlite_backend():
        return _enqueue_sqlite(task_name, args)
    else:
        return _enqueue_celery(task_name, args)


def _enqueue_sqlite(task_name: str, args: list) -> TaskHandle:
    """Insert a task into the job_queue table with retry on lock."""
    import sqlite3

    from app.sqlite_kv import _DB_PATH

    task_id = str(uuid.uuid4())

    max_retries = 5
    for attempt in range(max_retries):
        conn = sqlite3.connect(_DB_PATH, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                "INSERT INTO job_queue (id, task_name, args_json, status, priority, created_at) "
                "VALUES (?, ?, ?, 'pending', 0, datetime('now'))",
                (task_id, task_name, json.dumps(args)),
            )
            conn.commit()
            logger.info(f"Enqueued SQLite task {task_id} ({task_name})")
            return TaskHandle(task_id)
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                logger.warning(
                    f"SQLite locked on enqueue attempt {attempt + 1}/{max_retries}, "
                    f"retrying in {0.5 * (attempt + 1)}s..."
                )
                time.sleep(0.5 * (attempt + 1))
            else:
                raise
        finally:
            conn.close()

    # Should not reach here, but just in case
    raise sqlite3.OperationalError("database is locked after all retries")


def _enqueue_celery(task_name: str, args: list) -> TaskHandle:
    """Enqueue via Celery send_task."""
    from app.celery_app import celery_app

    result = celery_app.send_task(task_name, args=args)
    logger.info(f"Enqueued Celery task {result.id} ({task_name})")
    return TaskHandle(result.id)
