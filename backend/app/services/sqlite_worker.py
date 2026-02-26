"""In-process job runner backed by SQLite job_queue table.

In-process job runner using a ThreadPoolExecutor(max_workers=1).
Also runs periodic tasks (watchdog, planner tick, PR polling).
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.sqlite_kv import _DB_PATH

logger = logging.getLogger(__name__)

# Worker identity for claiming tasks
_WORKER_ID = f"sqlite-worker-{uuid.uuid4().hex[:8]}"


class SQLiteWorker:
    """In-process job runner backed by SQLite job_queue table."""

    def __init__(self, poll_interval: float = 0.5, max_workers: int = 1):
        self.poll_interval = poll_interval
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, Callable] = {}
        self._periodic_tasks: list[tuple[str, float, Callable]] = []
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def register_task(self, name: str, func: Callable) -> None:
        """Register a task function by name."""
        self._tasks[name] = func
        logger.debug(f"Registered task: {name}")

    def register_periodic(self, name: str, interval: float, func: Callable) -> None:
        """Register a periodic task (replaces Celery Beat)."""
        self._periodic_tasks.append((name, interval, func))
        logger.debug(f"Registered periodic task: {name} (every {interval}s)")

    def start(self) -> None:
        """Start the worker daemon threads."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="sqlite-worker-poll"
        )
        self._poll_thread.start()

        if self._periodic_tasks:
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True, name="sqlite-worker-scheduler"
            )
            self._scheduler_thread.start()

        logger.info(
            f"SQLite worker started (id={_WORKER_ID}, "
            f"tasks={list(self._tasks.keys())}, "
            f"periodic={[t[0] for t in self._periodic_tasks]})"
        )

    def stop(self) -> None:
        """Gracefully stop the worker."""
        if not self._running:
            return

        logger.info("Stopping SQLite worker...")
        self._running = False
        self._stop_event.set()

        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)

        self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("SQLite worker stopped")

    def _get_conn(self) -> sqlite3.Connection:
        """Get a SQLite connection with WAL mode."""
        conn = sqlite3.connect(_DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _poll_loop(self) -> None:
        """Main polling loop: claim and execute pending tasks.

        When max_workers > 1, the loop continues claiming tasks without sleeping
        until no more pending tasks are available, enabling parallel execution.
        """
        while self._running and not self._stop_event.is_set():
            try:
                task = self._claim_next_task()
                if task:
                    task_id, task_name, args_json = task
                    args = json.loads(args_json)

                    func = self._tasks.get(task_name)
                    if func:
                        self._executor.submit(
                            self._execute_task, task_id, task_name, func, args
                        )
                        # When parallel enabled, immediately try claiming more
                        if self.max_workers > 1:
                            continue
                    else:
                        logger.error(f"Unknown task: {task_name} (id={task_id})")
                        self._mark_failed(task_id, f"Unknown task: {task_name}")
                else:
                    # No pending tasks, sleep
                    self._stop_event.wait(timeout=self.poll_interval)

            except Exception as e:
                logger.error(f"Poll loop error: {e}", exc_info=True)
                self._stop_event.wait(timeout=1.0)

    def _claim_next_task(self) -> tuple[str, str, str] | None:
        """Atomically claim the next pending task.

        Uses UPDATE...RETURNING with a subquery for a single atomic operation
        (no race window between SELECT and UPDATE).

        Returns (task_id, task_name, args_json) or None.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "UPDATE job_queue SET status = 'claimed', claimed_by = ?, "
                "claimed_at = datetime('now') "
                "WHERE id = ("
                "  SELECT id FROM job_queue WHERE status = 'pending' "
                "  ORDER BY priority DESC, created_at ASC LIMIT 1"
                ") "
                "RETURNING id, task_name, args_json",
                (_WORKER_ID,),
            ).fetchone()
            conn.commit()
            return (row[0], row[1], row[2]) if row else None
        finally:
            conn.close()

    def _execute_task(
        self, task_id: str, task_name: str, func: Callable, args: list
    ) -> None:
        """Execute a claimed task and update its status."""
        logger.info(f"Executing task {task_name} (id={task_id})")
        try:
            result = func(*args)
            self._mark_completed(task_id, result)
            logger.info(f"Task {task_name} completed (id={task_id})")
        except Exception as e:
            logger.error(f"Task {task_name} failed (id={task_id}): {e}", exc_info=True)
            self._mark_failed(task_id, str(e))

    def _mark_completed(self, task_id: str, result) -> None:
        """Mark a task as completed with its result."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE job_queue SET status = 'completed', "
                "completed_at = datetime('now'), result_json = ? "
                "WHERE id = ?",
                (json.dumps(result) if result is not None else None, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE job_queue SET status = 'failed', "
                "completed_at = datetime('now'), result_json = ? "
                "WHERE id = ?",
                (json.dumps({"error": error[:1000]}), task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _scheduler_loop(self) -> None:
        """Run periodic tasks at their specified intervals."""
        last_run: dict[str, float] = {}

        while self._running and not self._stop_event.is_set():
            now = time.monotonic()

            for name, interval, func in self._periodic_tasks:
                last = last_run.get(name, 0)
                if now - last >= interval:
                    last_run[name] = now
                    try:
                        self._executor.submit(self._run_periodic, name, func)
                    except Exception as e:
                        logger.error(f"Failed to schedule periodic task {name}: {e}")

            self._stop_event.wait(timeout=0.5)

    def _run_periodic(self, name: str, func: Callable) -> None:
        """Execute a periodic task."""
        try:
            func()
        except Exception as e:
            logger.error(f"Periodic task {name} failed: {e}", exc_info=True)


# Global worker instance (created lazily)
_worker: SQLiteWorker | None = None


def get_worker() -> SQLiteWorker:
    """Get or create the global SQLite worker.

    Reads max_parallel_jobs from smartkanban.yaml to configure the thread pool.
    """
    global _worker
    if _worker is None:
        max_workers = 1
        try:
            from app.services.config_service import ConfigService

            config = ConfigService().load_config()
            max_workers = config.execute_config.max_parallel_jobs
        except Exception:
            pass  # Fall back to 1
        _worker = SQLiteWorker(max_workers=max_workers)
        if max_workers > 1:
            logger.info(f"Parallel execution enabled: max_parallel_jobs={max_workers}")
    return _worker


def setup_worker() -> SQLiteWorker:
    """Set up the SQLite worker with all registered tasks.

    Called during FastAPI lifespan.
    """
    worker = get_worker()

    # Register task functions (import here to avoid circular imports)
    from app.worker import (
        _execute_ticket_task_impl,
        _resume_ticket_task_impl,
        _verify_ticket_task_impl,
    )

    def execute_ticket_wrapper(job_id: str) -> dict:
        """Wrapper that sets up streaming context for execute_ticket."""
        from app.models.job import JobStatus
        from app.state_machine import TicketState
        from app.worker import (
            get_job_with_ticket,
            set_current_job,
            stream_finished,
            transition_ticket_sync,
            update_job_finished,
        )

        set_current_job(job_id)
        try:
            return _execute_ticket_task_impl(job_id)
        except Exception as e:
            logger.error(f"execute_ticket crashed for job {job_id}: {e}", exc_info=True)
            try:
                update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
            except Exception:
                pass
            try:
                result = get_job_with_ticket(job_id)
                if result:
                    _, ticket = result
                    transition_ticket_sync(
                        ticket.id,
                        TicketState.BLOCKED,
                        reason=f"Execution crashed: {e}",
                        actor_id="execute_worker",
                    )
            except Exception:
                pass
            return {"job_id": job_id, "status": "failed", "error": str(e)}
        finally:
            stream_finished(job_id)
            set_current_job(None)

    def verify_ticket_wrapper(job_id: str) -> dict:
        """Wrapper for verify_ticket."""
        from app.models.job import JobStatus
        from app.state_machine import TicketState
        from app.worker import (
            get_job_with_ticket,
            transition_ticket_sync,
            update_job_finished,
        )

        try:
            return _verify_ticket_task_impl(job_id)
        except Exception as e:
            logger.error(f"verify_ticket crashed for job {job_id}: {e}", exc_info=True)
            try:
                update_job_finished(job_id, JobStatus.FAILED, exit_code=1)
            except Exception:
                pass
            try:
                result = get_job_with_ticket(job_id)
                if result:
                    _, ticket = result
                    transition_ticket_sync(
                        ticket.id,
                        TicketState.BLOCKED,
                        reason=f"Verification crashed: {e}",
                        actor_id="verify_worker",
                    )
            except Exception:
                pass
            return {"job_id": job_id, "status": "failed", "error": str(e)}

    def resume_ticket_wrapper(job_id: str) -> dict:
        """Wrapper for resume_ticket."""
        return _resume_ticket_task_impl(job_id)

    worker.register_task("execute_ticket", execute_ticket_wrapper)
    worker.register_task("verify_ticket", verify_ticket_wrapper)
    worker.register_task("resume_ticket", resume_ticket_wrapper)

    # Register periodic tasks (replaces Celery Beat)
    def run_job_watchdog():
        from app.services.job_watchdog_service import run_job_watchdog

        run_job_watchdog()

    def run_planner_tick():
        from app.services.planner_tick_sync import (
            PlannerLockError,
            run_planner_tick_sync,
        )

        try:
            run_planner_tick_sync()
        except PlannerLockError:
            pass  # Another tick in progress

    def run_poll_pr_statuses():
        from app.worker import poll_pr_statuses

        poll_pr_statuses()

    worker.register_periodic("job_watchdog", 15.0, run_job_watchdog)
    worker.register_periodic("planner_tick", 2.0, run_planner_tick)
    worker.register_periodic("poll_pr_statuses", 300.0, run_poll_pr_statuses)

    return worker
