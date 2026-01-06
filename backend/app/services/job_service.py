"""Service layer for Job operations."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.celery_app import celery_app
from app.exceptions import ResourceNotFoundError
from app.models.job import Job, JobKind, JobStatus
from app.models.ticket import Ticket
from app.services.workspace_service import WorkspaceService

# Base directory for fallback logs (relative to backend directory)
FALLBACK_LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


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
        # Verify the ticket exists
        result = await self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Create the job record
        job = Job(
            ticket_id=ticket_id,
            kind=kind.value,
            status=JobStatus.QUEUED.value,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        # Enqueue the Celery task (import here to avoid circular dependency)
        from app.worker import execute_ticket_task, verify_ticket_task

        if kind == JobKind.EXECUTE:
            task = execute_ticket_task.delay(job.id)
        else:
            task = verify_ticket_task.delay(job.id)

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

        Args:
            log_path: The relative path to the log file

        Returns:
            The log content as a string, or None if no logs available
        """
        if not log_path:
            return None

        # Try repo root first (for worktree logs)
        repo_path = WorkspaceService.get_repo_path()
        full_path = repo_path / log_path

        if full_path.exists():
            try:
                return full_path.read_text()
            except OSError:
                pass

        # Fall back to backend directory (for legacy logs)
        backend_path = Path(__file__).parent.parent.parent / log_path
        if backend_path.exists():
            try:
                return backend_path.read_text()
            except OSError:
                pass

        return None
