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


def _check_budget_sync(job_id: str) -> None:
    """Check if the goal's budget allows execution (sync, best-effort).

    Queries the goal's CostBudget and total spend to warn/block if over budget.
    Only applies to execute tasks. Logs a warning if over budget but does not
    block (to avoid breaking existing workflows).
    """
    try:
        from app.database_sync import get_sync_db
        from app.models.job import Job

        with get_sync_db() as db:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job or not job.ticket_id:
                return

            from app.models.ticket import Ticket

            ticket = db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
            if not ticket or not ticket.goal_id:
                return

            from app.models.cost_budget import CostBudget

            budget = (
                db.query(CostBudget)
                .filter(CostBudget.goal_id == ticket.goal_id)
                .first()
            )
            if not budget or budget.total_budget is None:
                return

            from sqlalchemy import func

            from app.models.agent_session import AgentSession

            total_spent = (
                db.query(func.coalesce(func.sum(AgentSession.estimated_cost_usd), 0))
                .join(Ticket)
                .filter(Ticket.goal_id == ticket.goal_id)
                .scalar()
            )
            total_spent = float(total_spent or 0)

            if total_spent >= budget.total_budget:
                logger.warning(
                    f"Budget exceeded for goal {ticket.goal_id}: "
                    f"spent=${total_spent:.2f} >= budget=${budget.total_budget:.2f}. "
                    f"Job {job_id} will proceed but may incur overage."
                )
            elif (
                budget.warning_threshold
                and total_spent >= budget.total_budget * budget.warning_threshold
            ):
                logger.warning(
                    f"Budget warning for goal {ticket.goal_id}: "
                    f"spent=${total_spent:.2f} / budget=${budget.total_budget:.2f} "
                    f"({total_spent / budget.total_budget * 100:.0f}% used)"
                )
    except Exception as e:
        logger.debug(f"Budget check skipped for job {job_id}: {e}")


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

    # Check budget before enqueuing execute tasks
    if task_name == "execute_ticket" and args:
        _check_budget_sync(args[0])

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
