"""API router for Job endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.job import (
    CancelJobResponse,
    JobDetailResponse,
    JobStatus,
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
