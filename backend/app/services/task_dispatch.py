"""Unified task dispatch for both Celery and SQLite backends.

Replaces direct celery_app.send_task() / .delay() calls throughout the codebase.
"""

import json
import logging
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
    """Insert a task into the job_queue table."""
    import sqlite3

    from app.sqlite_kv import _DB_PATH

    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            "INSERT INTO job_queue (id, task_name, args_json, status, priority, created_at) "
            "VALUES (?, ?, ?, 'pending', 0, datetime('now'))",
            (task_id, task_name, json.dumps(args)),
        )
        conn.commit()
        logger.info(f"Enqueued SQLite task {task_id} ({task_name})")
    finally:
        conn.close()

    return TaskHandle(task_id)


def _enqueue_celery(task_name: str, args: list) -> TaskHandle:
    """Enqueue via Celery send_task."""
    from app.celery_app import celery_app

    result = celery_app.send_task(task_name, args=args)
    logger.info(f"Enqueued Celery task {result.id} ({task_name})")
    return TaskHandle(result.id)
