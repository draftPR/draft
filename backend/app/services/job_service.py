"""Service layer for Job operations."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ResourceNotFoundError, ValidationError
from app.models.job import Job, JobKind, JobStatus
from app.models.ticket import Ticket
from app.schemas.job import QueuedJobResponse, QueueStatusResponse
from app.services.workspace_service import WorkspaceService

# Base directory for fallback logs (relative to backend directory)
FALLBACK_LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

# Maximum log file size to read (2MB)
MAX_LOG_BYTES = 2_000_000

# Job rate limiting (prevent spam/runaway tickets)
MAX_JOBS_PER_TICKET_PER_HOUR = 10
MAX_EXECUTE_JOBS_PER_TICKET_PER_DAY = 50


def _safe_read_file(base_path: Path, allowed_root: Path, relpath: str) -> str | None:
    """Safely read a file, enforcing it is under allowed_root.

    Args:
        base_path: Base path to prepend to relpath
        allowed_root: Root directory that file must be under
        relpath: Relative path to the file

    Returns:
        File content if safe and exists, None otherwise
    """
    rel = Path(relpath)

    # Reject absolute paths
    if rel.is_absolute():
        return None

    # Resolve paths to canonical form
    allowed_canonical = allowed_root.resolve(strict=False)
    target = (base_path / rel).resolve(strict=False)

    # Enforce target is under allowed_root
    try:
        common = os.path.commonpath([str(target), str(allowed_canonical)])
    except ValueError:
        return None

    if common != str(allowed_canonical):
        return None

    if not target.is_file():
        return None

    try:
        size = target.stat().st_size
        if size > MAX_LOG_BYTES:
            with target.open("rb") as f:
                data = f.read(MAX_LOG_BYTES)
            return data.decode("utf-8", errors="replace") + "\n\n[truncated]"
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _safe_read_absolute(target: Path) -> str | None:
    """Safely read an absolute file path with size cap."""
    if not target.is_file():
        return None
    try:
        size = target.stat().st_size
        if size > MAX_LOG_BYTES:
            with target.open("rb") as f:
                data = f.read(MAX_LOG_BYTES)
            return data.decode("utf-8", errors="replace") + "\n\n[truncated]"
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class JobService:
    """Service class for Job business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self, ticket_id: str, kind: JobKind, variant: str | None = None
    ) -> Job:
        """
        Create a new job and enqueue the corresponding Celery task.

        Includes rate limiting to prevent runaway tickets.

        Args:
            ticket_id: The UUID of the ticket
            kind: The kind of job (execute or verify)
            variant: Optional execution variant (default, plan, qa, review)

        Returns:
            The created Job instance with celery_task_id set

        Raises:
            ResourceNotFoundError: If the ticket is not found
            ValidationError: If rate limit exceeded
        """
        # Verify the ticket exists and get its board_id
        # CRITICAL: Use SELECT FOR UPDATE to prevent race conditions in rate limiting
        # This locks the ticket row until transaction commits, serializing job creation
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # RATE LIMITING: Check hourly limit (protected by row lock above)
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        hourly_result = await self.db.execute(
            select(func.count(Job.id))
            .where(Job.ticket_id == ticket_id)
            .where(Job.kind == kind.value)
            .where(Job.created_at >= one_hour_ago)
        )
        recent_jobs_hour = hourly_result.scalar()

        if recent_jobs_hour >= MAX_JOBS_PER_TICKET_PER_HOUR:
            raise ValidationError(
                f"Rate limit exceeded: {recent_jobs_hour} {kind.value} jobs in past hour. "
                f"Max {MAX_JOBS_PER_TICKET_PER_HOUR} per hour per ticket."
            )

        # RATE LIMITING: Check daily limit for EXECUTE jobs (expensive)
        if kind == JobKind.EXECUTE:
            one_day_ago = datetime.now(UTC) - timedelta(days=1)
            daily_result = await self.db.execute(
                select(func.count(Job.id))
                .where(Job.ticket_id == ticket_id)
                .where(Job.kind == JobKind.EXECUTE.value)
                .where(Job.created_at >= one_day_ago)
            )
            recent_jobs_day = daily_result.scalar()

            if recent_jobs_day >= MAX_EXECUTE_JOBS_PER_TICKET_PER_DAY:
                raise ValidationError(
                    f"Daily execute limit exceeded: {recent_jobs_day} execute jobs in past 24h. "
                    f"Max {MAX_EXECUTE_JOBS_PER_TICKET_PER_DAY} per day per ticket."
                )

        # Create the job record with board_id from ticket for permission scoping
        job = Job(
            ticket_id=ticket_id,
            board_id=ticket.board_id,  # Inherit board_id from ticket
            kind=kind.value,
            status=JobStatus.QUEUED.value,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        # CRITICAL: Commit the job BEFORE enqueuing Celery task
        # This ensures the Celery worker (sync session) can see the job
        # Without this, async/sync session isolation causes "Job not found" errors
        await self.db.commit()

        # Enqueue the task via unified dispatch (supports SQLite and Celery backends)
        from app.services.task_dispatch import enqueue_task

        task_names = {
            JobKind.EXECUTE: "execute_ticket",
            JobKind.VERIFY: "verify_ticket",
            JobKind.RESUME: "resume_ticket",
        }
        task_name = task_names.get(kind)
        if not task_name:
            raise ValueError(f"Unknown job kind: {kind}")
        task = enqueue_task(task_name, args=[job.id])

        # Store the task ID for later reference (e.g., cancellation)
        job.celery_task_id = task.id

        # Commit again to save the celery_task_id
        await self.db.commit()
        await self.db.refresh(job)

        return job

    async def get_job_by_id(self, job_id: str) -> Job:
        """
        Get a job by its ID.

        Args:
            job_id: The UUID of the job

        Returns:
            The Job instance

        Raises:
            ResourceNotFoundError: If the job is not found
        """
        result = await self.db.execute(
            select(Job).where(Job.id == job_id).options(selectinload(Job.ticket))
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ResourceNotFoundError("Job", job_id)
        return job

    async def get_jobs_for_ticket(self, ticket_id: str) -> list[Job]:
        """
        Get all jobs for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            List of Job instances ordered by created_at descending

        Raises:
            ResourceNotFoundError: If the ticket is not found
        """
        # Verify the ticket exists
        result = await self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Get all jobs for the ticket
        result = await self.db.execute(
            select(Job)
            .where(Job.ticket_id == ticket_id)
            .order_by(Job.created_at.desc())
        )
        return list(result.scalars().all())

    async def cancel_job(self, job_id: str) -> Job:
        """
        Cancel a job (actively kills running subprocesses).

        This will:
        1. Mark the job as canceled in the database
        2. Kill any running subprocess for this job
        3. Attempt to revoke the Celery task

        Args:
            job_id: The UUID of the job

        Returns:
            The updated Job instance

        Raises:
            ResourceNotFoundError: If the job is not found
        """
        import asyncio
        import logging

        logger = logging.getLogger(__name__)
        job = await self.get_job_by_id(job_id)

        # Only cancel if not already in a terminal state
        if job.status in [
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELED.value,
        ]:
            return job

        # Mark as canceled in database FIRST (so worker polls see it)
        job.status = JobStatus.CANCELED.value
        await self.db.flush()

        # Kill any running subprocess
        try:
            from app.worker import kill_job_process

            killed = await asyncio.to_thread(kill_job_process, job_id)
            if killed:
                logger.info(f"Successfully killed subprocess for job {job_id}")
            else:
                logger.warning(f"No active subprocess found for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to kill subprocess for job {job_id}: {e}")

        await self.db.refresh(job)
        return job

    def read_job_logs(self, log_path: str | None) -> str | None:
        """
        Read the log content for a job (synchronous version).

        Security:
            - Reads from central data dir, legacy .smartkanban/, or backend/logs/
            - Validates canonical path is under allowed directory
            - Caps file size to prevent memory exhaustion

        Args:
            log_path: The path to the log file (absolute or relative)

        Returns:
            The log content as a string, or None if no logs available
        """
        if not log_path:
            return None

        from app.data_dir import get_data_dir

        # If it's an absolute path under the central data dir, read directly
        log_p = Path(log_path)
        if log_p.is_absolute():
            data_dir = get_data_dir()
            try:
                log_p.resolve().relative_to(data_dir.resolve())
                if log_p.is_file():
                    return _safe_read_absolute(log_p)
            except ValueError:
                pass

        # Try central data dir (for new logs)
        data_dir = get_data_dir()
        content = _safe_read_file(data_dir, data_dir / "logs", log_path)
        if content is not None:
            return content

        # Try repo root (legacy .smartkanban/ logs)
        repo_path = WorkspaceService.get_repo_path()
        smartkanban_root = repo_path / ".smartkanban"
        content = _safe_read_file(repo_path, smartkanban_root, log_path)
        if content is not None:
            return content

        # Fall back to backend/logs/ directory (for legacy fallback logs)
        backend_root = Path(__file__).parent.parent.parent
        content = _safe_read_file(backend_root, FALLBACK_LOGS_DIR, log_path)
        return content

    async def read_job_logs_async(self, log_path: str | None) -> str | None:
        """
        Read the log content for a job (async version - non-blocking).

        Wraps file I/O in asyncio.to_thread() to avoid blocking the event loop.

        Security:
            - Only reads files under <repo_root>/.smartkanban/ or backend/logs/
            - Rejects absolute paths
            - Validates canonical path is under allowed directory
            - Caps file size to prevent memory exhaustion

        Args:
            log_path: The relative path to the log file

        Returns:
            The log content as a string, or None if no logs available
        """
        import asyncio

        return await asyncio.to_thread(self.read_job_logs, log_path)

    async def get_queue_status(self) -> QueueStatusResponse:
        """
        Get the current queue status showing running and queued jobs.

        Returns:
            QueueStatusResponse with running and queued jobs including ticket info
        """
        # Get running jobs (ordered by started_at)
        running_result = await self.db.execute(
            select(Job)
            .where(Job.status == JobStatus.RUNNING.value)
            .options(selectinload(Job.ticket))
            .order_by(Job.started_at.asc())
        )
        running_jobs = list(running_result.scalars().all())

        # Get queued jobs (ordered by created_at - FIFO)
        queued_result = await self.db.execute(
            select(Job)
            .where(Job.status == JobStatus.QUEUED.value)
            .options(selectinload(Job.ticket))
            .order_by(Job.created_at.asc())
        )
        queued_jobs = list(queued_result.scalars().all())

        # Build response
        running_responses = [
            QueuedJobResponse(
                id=job.id,
                ticket_id=job.ticket_id,
                ticket_title=job.ticket.title if job.ticket else "Unknown",
                kind=JobKind(job.kind),
                status=JobStatus(job.status),
                created_at=job.created_at,
                started_at=job.started_at,
                queue_position=None,  # Running jobs have no queue position
            )
            for job in running_jobs
        ]

        queued_responses = [
            QueuedJobResponse(
                id=job.id,
                ticket_id=job.ticket_id,
                ticket_title=job.ticket.title if job.ticket else "Unknown",
                kind=JobKind(job.kind),
                status=JobStatus(job.status),
                created_at=job.created_at,
                started_at=job.started_at,
                queue_position=idx + 1,  # 1-based position
            )
            for idx, job in enumerate(queued_jobs)
        ]

        return QueueStatusResponse(
            running=running_responses,
            queued=queued_responses,
            total_running=len(running_responses),
            total_queued=len(queued_responses),
        )
