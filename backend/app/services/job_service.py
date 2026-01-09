"""Service layer for Job operations."""

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.exceptions import ResourceNotFoundError
from app.models.job import Job, JobKind, JobStatus
from app.models.ticket import Ticket
from app.schemas.job import QueuedJobResponse, QueueStatusResponse
from app.services.workspace_service import WorkspaceService

# Base directory for fallback logs (relative to backend directory)
FALLBACK_LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

# Maximum log file size to read (2MB)
MAX_LOG_BYTES = 2_000_000


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
    except (OSError, IOError):
        return None


class JobService:
    """Service class for Job business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, ticket_id: str, kind: JobKind) -> Job:
        """
        Create a new job and enqueue the corresponding Celery task.

        Args:
            ticket_id: The UUID of the ticket
            kind: The kind of job (execute or verify)

        Returns:
            The created Job instance with celery_task_id set

        Raises:
            ResourceNotFoundError: If the ticket is not found
        """
        # Verify the ticket exists and get its board_id
        result = await self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

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

        # Enqueue the Celery task (import here to avoid circular dependency)
        from app.worker import execute_ticket_task, resume_ticket_task, verify_ticket_task

        if kind == JobKind.EXECUTE:
            task = execute_ticket_task.delay(job.id)
        elif kind == JobKind.VERIFY:
            task = verify_ticket_task.delay(job.id)
        elif kind == JobKind.RESUME:
            task = resume_ticket_task.delay(job.id)
        else:
            raise ValueError(f"Unknown job kind: {kind}")

        # Store the Celery task ID for later reference (e.g., cancellation)
        job.celery_task_id = task.id
        await self.db.flush()
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
        Cancel a job (best-effort).

        This will:
        1. Mark the job as canceled in the database
        2. Attempt to revoke the Celery task

        Args:
            job_id: The UUID of the job

        Returns:
            The updated Job instance

        Raises:
            ResourceNotFoundError: If the job is not found
        """
        job = await self.get_job_by_id(job_id)

        # Only cancel if not already in a terminal state
        if job.status in [
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELED.value,
        ]:
            return job

        # Mark as canceled in database
        job.status = JobStatus.CANCELED.value

        # Attempt to revoke the Celery task (best-effort)
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)

        await self.db.flush()
        await self.db.refresh(job)

        return job

    def read_job_logs(self, log_path: str | None) -> str | None:
        """
        Read the log content for a job.

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
        if not log_path:
            return None

        # Try repo root first (for worktree logs under .smartkanban/)
        repo_path = WorkspaceService.get_repo_path()
        smartkanban_root = repo_path / ".smartkanban"
        content = _safe_read_file(repo_path, smartkanban_root, log_path)
        if content is not None:
            return content

        # Fall back to backend/logs/ directory (for legacy fallback logs)
        backend_root = Path(__file__).parent.parent.parent
        content = _safe_read_file(backend_root, FALLBACK_LOGS_DIR, log_path)
        return content

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
