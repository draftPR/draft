"""API router for maintenance operations."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.merge import CleanupRequest, CleanupResponse
from app.services.cleanup_service import CleanupService

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class WatchdogResponse(BaseModel):
    """Response from watchdog run."""

    stale_jobs_recovered: int
    timed_out_jobs_recovered: int
    stuck_queued_jobs_failed: int
    lost_tasks_reenqueued: int = 0  # Jobs re-enqueued due to lost Celery tasks
    tickets_blocked: int
    details: list[str]


@router.post(
    "/cleanup",
    response_model=CleanupResponse,
    summary="Run cleanup of stale worktrees and old evidence",
)
async def run_cleanup(
    data: CleanupRequest,
    db: AsyncSession = Depends(get_db),
) -> CleanupResponse:
    """
    Run cleanup of stale worktrees and old evidence files.

    By default runs in dry_run mode, which only reports what would be deleted.
    Set dry_run=false to actually perform deletions.

    Cleanup rules (from smartkanban.yaml cleanup_config):
    - worktree_ttl_days: Delete worktrees older than this
    - evidence_ttl_days: Delete evidence files older than this
    - max_worktrees: Maximum number of active worktrees (not enforced yet)

    Safety:
    - Only deletes files under .smartkanban/
    - Uses `git worktree remove` + `git worktree prune`
    - Never deletes worktrees for tickets in executing/verifying/needs_human
    - Creates audit events for deletions
    - Orphaned directories (not in DB) are also cleaned up
    """
    service = CleanupService(db)

    result = await service.run_full_cleanup(
        dry_run=data.dry_run,
        delete_worktrees=data.delete_worktrees,
        delete_evidence=data.delete_evidence,
    )

    return CleanupResponse(
        dry_run=data.dry_run,
        worktrees_deleted=result.worktrees_deleted,
        worktrees_failed=result.worktrees_failed,
        worktrees_skipped=result.worktrees_skipped,
        evidence_files_deleted=result.evidence_files_deleted,
        evidence_files_failed=result.evidence_files_failed,
        bytes_freed=result.bytes_freed,
        details=result.details,
    )


class ReenqueueResponse(BaseModel):
    """Response from re-enqueue operation."""

    jobs_reenqueued: int
    details: list[str]


@router.post(
    "/reenqueue-lost-jobs",
    response_model=ReenqueueResponse,
    summary="[DEV ONLY] Re-enqueue jobs that are queued in DB but missing from Celery",
)
async def reenqueue_lost_jobs(
    db: AsyncSession = Depends(get_db),
) -> ReenqueueResponse:
    """
    Re-enqueue jobs that are stuck in QUEUED status but missing from the Celery queue.

    This can happen if:
    - Redis was restarted/flushed
    - The Celery worker was down when jobs were created
    - Task messages were lost

    For each QUEUED job, this re-sends the Celery task and updates the celery_task_id.
    """
    from sqlalchemy import select

    from app.models.job import Job, JobKind, JobStatus
    from app.services.task_dispatch import enqueue_task

    result = await db.execute(select(Job).where(Job.status == JobStatus.QUEUED.value))
    queued_jobs = result.scalars().all()

    details = []
    count = 0

    task_names = {
        JobKind.EXECUTE.value: "execute_ticket",
        JobKind.VERIFY.value: "verify_ticket",
        JobKind.RESUME.value: "resume_ticket",
    }

    for job in queued_jobs:
        try:
            # Re-enqueue based on job kind using send_task
            task_name = task_names.get(job.kind)
            if not task_name:
                details.append(f"Job {job.id}: Unknown kind {job.kind}")
                continue

            task = enqueue_task(task_name, args=[job.id])

            # Update task ID
            job.celery_task_id = task.id
            details.append(f"Job {job.id} ({job.kind}): Re-enqueued as {task.id}")
            count += 1
        except Exception as e:
            details.append(f"Job {job.id}: Error re-enqueueing: {e}")

    await db.commit()

    return ReenqueueResponse(
        jobs_reenqueued=count,
        details=details,
    )


@router.post(
    "/watchdog/run",
    response_model=WatchdogResponse,
    summary="[DEV ONLY] Manually run job watchdog",
)
async def run_watchdog() -> WatchdogResponse:
    """
    Manually trigger the job watchdog task.

    This is a DEV/DEBUG endpoint for testing watchdog behavior.
    In production, the watchdog runs automatically via Celery beat every 15s.

    The watchdog checks for:
    1. RUNNING jobs with stale heartbeat (no update in 2 minutes)
    2. RUNNING jobs that exceeded their timeout_seconds
    3. QUEUED jobs for 30+ seconds - re-enqueues lost Celery tasks
    4. QUEUED jobs stuck for 2+ minutes - fails them as worker may be down

    For stuck jobs, it either:
    - Re-enqueues the Celery task (if task was lost from Redis)
    - Marks the job as FAILED and transitions ticket to BLOCKED
    """
    from app.services.job_watchdog_service import run_job_watchdog

    result = run_job_watchdog()

    return WatchdogResponse(
        stale_jobs_recovered=result.stale_jobs_recovered,
        timed_out_jobs_recovered=result.timed_out_jobs_recovered,
        stuck_queued_jobs_failed=result.stuck_queued_jobs_failed,
        lost_tasks_reenqueued=result.lost_tasks_reenqueued,
        tickets_blocked=result.tickets_blocked,
        details=result.details,
    )
