"""Service for monitoring and recovering stuck jobs."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database_sync import get_sync_db
from app.models.job import Job, JobStatus
from app.models.ticket import Ticket
from app.state_machine import TicketState

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is UTC-aware. Returns None if input is None.

    SQLite stores datetimes without timezone info. This helper ensures
    we can safely compare database datetimes with timezone-aware now().
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetimes from DB are UTC
        return dt.replace(tzinfo=UTC)
    return dt


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert a datetime to naive UTC for SQLite comparisons.

    SQLite stores datetimes without timezone info. When comparing Python
    datetimes with SQLite columns, we need naive datetimes to avoid
    'can't subtract offset-naive and offset-aware datetimes' errors.
    """
    if dt.tzinfo is not None:
        # Convert to UTC and strip timezone
        return dt.replace(tzinfo=None)
    return dt


# Default thresholds
HEARTBEAT_STALE_SECONDS = 120  # Job is stale if no heartbeat in 2 minutes
QUEUED_REENQUEUE_SECONDS = 30  # Re-enqueue lost tasks after 30 seconds
QUEUED_STALE_MINUTES = 2  # Job is stuck in queue if queued for 2 minutes (fail after this)
DEFAULT_JOB_TIMEOUT_SECONDS = 900  # 15 minutes default timeout

# SQLite retry config
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5


@dataclass
class WatchdogResult:
    """Result of a watchdog run."""

    stale_jobs_recovered: int = 0
    timed_out_jobs_recovered: int = 0
    stuck_queued_jobs_failed: int = 0
    missing_started_at_jobs: int = 0
    lost_tasks_reenqueued: int = 0  # Jobs re-enqueued due to lost Celery tasks
    tickets_blocked: int = 0
    details: list[str] = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


def run_job_watchdog() -> WatchdogResult:
    """Run the job watchdog to recover stuck jobs.

    This function checks for:
    1. RUNNING jobs with stale heartbeat (no update in HEARTBEAT_STALE_SECONDS)
    2. RUNNING jobs that exceeded their timeout_seconds
    3. RUNNING jobs missing started_at (data corruption or bug)
    4. QUEUED jobs that haven't been picked up in QUEUED_STALE_MINUTES

    For each stuck job:
    - Mark job as FAILED with reason
    - Transition associated ticket to BLOCKED (via proper transition function)
    - Uses transaction + retry for SQLite concurrency safety

    Returns:
        WatchdogResult with counts and details
    """
    result = WatchdogResult()

    with get_sync_db() as db:
        # Use UTC-aware datetime for Python operations
        now = datetime.now(UTC)
        # Use naive UTC for SQLite comparisons (SQLite stores naive datetimes)
        now_naive = _to_naive_utc(now)

        # 1. Find RUNNING jobs with stale heartbeat
        heartbeat_threshold = now_naive - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        stale_heartbeat_jobs = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.RUNNING.value,
                # Must have started_at to be considered for stale heartbeat
                Job.started_at.isnot(None),
                or_(
                    Job.last_heartbeat_at.is_(None),
                    Job.last_heartbeat_at < heartbeat_threshold,
                ),
            )
            .all()
        )

        for job in stale_heartbeat_jobs:
            _fail_job_with_retry(
                db=db,
                job=job,
                reason="Stale heartbeat - worker may have crashed",
                result=result,
                now=now,
            )
            result.stale_jobs_recovered += 1

        # 2. Find RUNNING jobs missing started_at (data corruption)
        # These are separate from stale heartbeat - they indicate a bug
        missing_started_at_jobs = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.RUNNING.value,
                Job.started_at.is_(None),
            )
            .all()
        )

        for job in missing_started_at_jobs:
            _fail_job_with_retry(
                db=db,
                job=job,
                reason="Running job missing started_at - possible data corruption",
                result=result,
                now=now,
            )
            result.missing_started_at_jobs += 1

        # 3. Find RUNNING jobs that exceeded timeout
        # Only check jobs that have valid started_at
        running_jobs_with_start = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.RUNNING.value,
                Job.started_at.isnot(None),
            )
            .all()
        )

        for job in running_jobs_with_start:
            timeout = job.timeout_seconds or DEFAULT_JOB_TIMEOUT_SECONDS
            # Safe: we know started_at is not None from the query
            # Use _ensure_utc to handle timezone-naive datetimes from SQLite
            elapsed = (now - _ensure_utc(job.started_at)).total_seconds()
            if elapsed > timeout:
                _fail_job_with_retry(
                    db=db,
                    job=job,
                    reason=f"Job timeout exceeded ({timeout}s, elapsed {int(elapsed)}s)",
                    result=result,
                    now=now,
                )
                result.timed_out_jobs_recovered += 1

        # 4. Re-enqueue jobs that may have lost their Celery tasks (30s threshold)
        # This catches jobs where the Celery task was lost from Redis but the DB shows queued
        reenqueue_threshold = now_naive - timedelta(seconds=QUEUED_REENQUEUE_SECONDS)
        potentially_lost_jobs = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.QUEUED.value,
                Job.created_at < reenqueue_threshold,
            )
            .all()
        )

        for job in potentially_lost_jobs:
            reenqueued = _reenqueue_lost_task(db, job, result)
            if reenqueued:
                result.lost_tasks_reenqueued += 1

        # 5. Find QUEUED jobs that haven't been picked up even after re-enqueue attempts
        # This is the final fallback - fail jobs stuck for too long
        queued_threshold = now_naive - timedelta(minutes=QUEUED_STALE_MINUTES)
        stuck_queued_jobs = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.QUEUED.value,
                Job.created_at < queued_threshold,
            )
            .all()
        )

        for job in stuck_queued_jobs:
            _fail_job_with_retry(
                db=db,
                job=job,
                reason=f"Stuck in queue for over {QUEUED_STALE_MINUTES} minutes - worker may be down",
                result=result,
                now=now,
            )
            result.stuck_queued_jobs_failed += 1

    logger.info(
        f"Watchdog completed: {result.stale_jobs_recovered} stale, "
        f"{result.timed_out_jobs_recovered} timed out, "
        f"{result.missing_started_at_jobs} missing started_at, "
        f"{result.lost_tasks_reenqueued} re-enqueued, "
        f"{result.stuck_queued_jobs_failed} stuck queued, "
        f"{result.tickets_blocked} tickets blocked"
    )

    return result


def _reenqueue_lost_task(db: Session, job: Job, result: WatchdogResult) -> bool:
    """Re-enqueue a Celery task for a job that may have lost its task.

    Checks if the job's Celery task is still in the queue/active. If not,
    creates a new Celery task for the job.

    Args:
        db: Database session
        job: The job to potentially re-enqueue
        result: WatchdogResult to update with details

    Returns:
        True if the task was re-enqueued, False if it was still active
    """
    from app.celery_app import celery_app
    from app.worker import execute_ticket_task, verify_ticket_task, resume_ticket_task
    from app.models.job import JobKind

    # Check if the Celery task is still pending/active
    if job.celery_task_id:
        try:
            task_result = celery_app.AsyncResult(job.celery_task_id)
            # If task is pending or started, it's still being processed
            if task_result.state in ("PENDING", "STARTED", "RETRY"):
                # Task exists, no need to re-enqueue
                return False
        except Exception as e:
            logger.warning(f"Error checking task status for job {job.id}: {e}")

    # Task is lost or never existed - re-enqueue
    try:
        task = None
        if job.kind == JobKind.EXECUTE.value:
            task = execute_ticket_task.delay(job.id)
        elif job.kind == JobKind.VERIFY.value:
            task = verify_ticket_task.delay(job.id)
        elif job.kind == JobKind.RESUME.value:
            task = resume_ticket_task.delay(job.id)

        if task:
            old_task_id = job.celery_task_id
            job.celery_task_id = task.id
            db.commit()
            logger.info(
                f"Re-enqueued lost Celery task for job {job.id} ({job.kind}): "
                f"old={old_task_id}, new={task.id}"
            )
            result.details.append(
                f"Job {job.id} ({job.kind}): Re-enqueued lost task (was {old_task_id})"
            )
            return True
        else:
            logger.warning(f"Unknown job kind for re-enqueue: {job.kind}")
            return False

    except Exception as e:
        logger.error(f"Failed to re-enqueue job {job.id}: {e}")
        result.details.append(f"Job {job.id} ({job.kind}): Failed to re-enqueue: {e}")
        return False


def _fail_job_with_retry(
    db: Session,
    job: Job,
    reason: str,
    result: WatchdogResult,
    now: datetime,
) -> None:
    """Mark a job as failed with SQLite retry logic.

    Uses transaction + retry to handle SQLite BUSY errors from
    concurrent worker/API writes.

    Args:
        db: Database session
        job: The job to fail
        reason: Reason for failure
        result: WatchdogResult to update
        now: Current timestamp
    """
    for attempt in range(MAX_RETRIES):
        try:
            _fail_job(db, job, reason, result, now)
            return
        except OperationalError as e:
            if "database is locked" in str(e) or "SQLITE_BUSY" in str(e):
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"SQLite busy, retrying job {job.id} fail (attempt {attempt + 1})"
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    db.rollback()
                else:
                    logger.error(f"Failed to fail job {job.id} after {MAX_RETRIES} attempts: {e}")
                    result.details.append(f"[RETRY FAILED] Job {job.id}: {reason}")
            else:
                raise


def _fail_job(
    db: Session,
    job: Job,
    reason: str,
    result: WatchdogResult,
    now: datetime,
) -> None:
    """Mark a job as failed and transition ticket to BLOCKED.

    Uses the proper transition function to ensure:
    - State machine rules are respected
    - Events are created consistently
    - Side effects are handled

    Args:
        db: Database session
        job: The job to fail
        reason: Reason for failure
        result: WatchdogResult to update
        now: Current timestamp
    """
    # Mark job as failed
    job.status = JobStatus.FAILED.value
    job.finished_at = now
    job.exit_code = -1

    result.details.append(f"Job {job.id} ({job.kind}): {reason}")

    # Get the ticket
    ticket = db.query(Ticket).filter(Ticket.id == job.ticket_id).first()
    if not ticket:
        db.commit()
        return

    # Only transition if not in terminal state
    if ticket.state in [TicketState.DONE.value, TicketState.ABANDONED.value]:
        db.commit()
        return

    # Commit job status first
    db.commit()

    # Use the proper transition function to maintain invariants
    # This ensures state machine rules and event creation are consistent
    from app.worker import transition_ticket_sync

    transition_ticket_sync(
        ticket_id=ticket.id,
        to_state=TicketState.BLOCKED,
        reason=f"Job {job.id} failed: {reason}",
        payload={
            "job_id": job.id,
            "job_kind": job.kind,
            "watchdog_reason": reason,
        },
        actor_id="job_watchdog",
        auto_verify=False,  # Don't auto-verify when blocking
    )

    result.tickets_blocked += 1
    result.details.append(f"Ticket {ticket.id} transitioned to BLOCKED")
