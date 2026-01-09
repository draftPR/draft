"""API router for Job endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ResourceNotFoundError, ValidationError
from app.models.job import JobKind
from app.schemas.job import (
    CancelJobResponse,
    JobCreateResponse,
    JobDetailResponse,
    JobStatus,
    QueueStatusResponse,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/queue",
    response_model=QueueStatusResponse,
    summary="Get queue status with running and queued jobs",
)
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
) -> QueueStatusResponse:
    """
    Get the current queue status showing which agents/jobs are running
    and which jobs are waiting in the queue.

    Returns:
        - running: List of currently running jobs with ticket info
        - queued: List of queued jobs in order (first = next to run)
    """
    service = JobService(db)
    return await service.get_queue_status()


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Get a job by ID",
)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobDetailResponse:
    """
    Get a job by its ID, including log content if available.
    """
    service = JobService(db)
    job = await service.get_job_by_id(job_id)
    logs = service.read_job_logs(job.log_path)

    return JobDetailResponse(
        id=job.id,
        ticket_id=job.ticket_id,
        kind=job.kind_enum,
        status=job.status_enum,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        exit_code=job.exit_code,
        log_path=job.log_path,
        logs=logs,
    )


@router.get(
    "/{job_id}/logs",
    response_class=PlainTextResponse,
    summary="Get raw logs for a job",
)
async def get_job_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """
    Get the raw log content for a job as plain text.
    """
    service = JobService(db)
    job = await service.get_job_by_id(job_id)
    logs = service.read_job_logs(job.log_path)

    if logs is None:
        return PlainTextResponse(content="No logs available yet.", status_code=200)

    return PlainTextResponse(content=logs)


@router.post(
    "/{job_id}/cancel",
    response_model=CancelJobResponse,
    summary="Cancel a job (best-effort)",
)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> CancelJobResponse:
    """
    Cancel a job (best-effort).

    This will mark the job as canceled in the database and attempt to
    revoke the Celery task. If the task is already running, it may
    complete before the cancellation takes effect.
    """
    service = JobService(db)
    job = await service.cancel_job(job_id)

    # Determine message based on original vs new status
    if job.status == JobStatus.CANCELED.value:
        message = "Job cancellation requested"
    else:
        message = f"Job already in terminal state: {job.status}"

    return CancelJobResponse(
        id=job.id,
        status=job.status_enum,
        message=message,
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Retry a failed job",
)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    Retry a failed job by creating a new job with the same kind.

    This will:
    1. Verify the original job exists and is in a terminal state (FAILED/CANCELED)
    2. Create a new job with the same kind for the same ticket
    3. Enqueue the new job to Celery

    Note: This creates a NEW job (new ID), it does not reuse the old job.
    """
    service = JobService(db)

    try:
        original_job = await service.get_job_by_id(job_id)
    except ResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Verify job is in terminal state
    if original_job.status not in [JobStatus.FAILED.value, JobStatus.CANCELED.value]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only retry FAILED or CANCELED jobs. Current status: {original_job.status}",
        )

    # Create new job with same kind
    try:
        new_job = await service.create_job(
            ticket_id=original_job.ticket_id,
            kind=JobKind(original_job.kind),
        )
        await db.commit()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create retry job: {str(e)}",
        )

    return JobCreateResponse(
        id=new_job.id,
        ticket_id=new_job.ticket_id,
        kind=new_job.kind_enum,
        status=new_job.status_enum,
        created_at=new_job.created_at,
        started_at=new_job.started_at,
        finished_at=new_job.finished_at,
        exit_code=new_job.exit_code,
        log_path=new_job.log_path,
        celery_task_id=new_job.celery_task_id,
    )
