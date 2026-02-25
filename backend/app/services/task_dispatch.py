"""Task dispatch via SQLite job_queue table.

Enqueues background tasks for the in-process SQLiteWorker to pick up.
"""

import json
import logging
import time
import uuid

logger = logging.getLogger(__name__)


class TaskHandle:
    """Opaque handle returned by enqueue_task.

    Has .id attribute for compatibility with job tracking.
    """

    def __init__(self, task_id: str):
        self.id = task_id


def enqueue_task(task_name: str, args: list | None = None) -> TaskHandle:
    """Enqueue a task into the SQLite job_queue table.

    Args:
        task_name: The task name (e.g., "execute_ticket", "verify_ticket")
        args: Positional arguments for the task

    Returns:
        TaskHandle with .id attribute (task ID string)
    """
    import sqlite3

    from app.sqlite_kv import _DB_PATH

    args = args or []
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
            logger.info(f"Enqueued task {task_id} ({task_name})")
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
