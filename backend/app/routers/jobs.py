"""API router for Job endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.exceptions import ResourceNotFoundError
from app.models.job import JobKind
from app.schemas.job import (
    CancelJobResponse,
    JobCreateResponse,
    JobDetailResponse,
    JobStatus,
    QueueStatusResponse,
)
from app.services.job_service import JobService
from app.services.log_normalizer import LogNormalizerService
from app.services.log_stream_service import LogLevel, log_stream_service

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
    # Use async version to avoid blocking event loop during file I/O
    logs = await service.read_job_logs_async(job.log_path)

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
    # Use async version to avoid blocking event loop during file I/O
    logs = await service.read_job_logs_async(job.log_path)

    if logs is None:
        return PlainTextResponse(content="No logs available yet.", status_code=200)

    return PlainTextResponse(content=logs)


@router.get(
    "/{job_id}/logs/stream",
    summary="Stream logs in real-time via SSE",
)
async def stream_job_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """
    Stream job logs in real-time using Server-Sent Events (SSE).

    This provides instant feedback during job execution - similar to
    vibe-kanban's WebSocket streaming but using SSE for simplicity.

    Events:
        - stdout: Standard output from executor
        - stderr: Standard error from executor
        - info: Informational messages
        - error: Error messages
        - finished: Job has completed

    The stream will:
    1. First send all historical messages (catch-up)
    2. Then stream live updates as they happen
    3. Close when job finishes or client disconnects

    Example client usage (JavaScript):
        const es = new EventSource('/api/jobs/{job_id}/logs/stream');
        es.addEventListener('stdout', (e) => console.log(e.data));
        es.addEventListener('finished', () => es.close());
    """
    # Verify job exists
    service = JobService(db)
    await service.get_job_by_id(job_id)

    async def event_generator():
        """Generate SSE events from log stream."""
        import json

        try:
            async for msg in log_stream_service.subscribe(job_id):
                # For progress events, include metadata as JSON
                if msg.level == LogLevel.PROGRESS:
                    data = json.dumps(
                        {
                            "content": msg.content,
                            "progress_pct": msg.progress_pct,
                            "stage": msg.stage,
                        }
                    )
                else:
                    data = msg.content

                yield {
                    "event": msg.level.value,
                    "data": data,
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": f"Stream error: {str(e)}",
            }

    return EventSourceResponse(
        event_generator(),
        ping=15,  # Send keepalive every 15 seconds
    )


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


@router.get(
    "/{job_id}/normalized-logs",
    summary="Get normalized, structured logs for a job",
)
async def get_normalized_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Get normalized, structured logs for a job.

    Returns a list of structured log entries parsed from raw agent output.
    Each entry has a semantic type (thinking, file_edit, command_run, etc.)
    and structured metadata for rich UI rendering.

    If normalized logs don't exist yet, returns an empty list.
    """
    service = JobService(db)

    # Verify job exists
    try:
        await service.get_job_by_id(job_id)
    except ResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Get normalized logs
    normalizer = LogNormalizerService()
    logs = await normalizer.get_normalized_logs(db, job_id)

    return [log.to_dict() for log in logs]


@router.post(
    "/{job_id}/normalize-logs",
    summary="Parse and normalize logs for a job",
)
async def normalize_logs(
    job_id: str,
    agent_type: str = "claude",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Parse raw logs and store normalized entries.

    This endpoint manually triggers log normalization. Normally this happens
    automatically after job completion, but this can be used to:
    - Re-parse logs with updated parser logic
    - Parse logs for old jobs that weren't normalized
    - Test parser changes

    Args:
        agent_type: Type of agent (claude, cursor, etc.) - determines parser
    """
    service = JobService(db)

    # Get job
    try:
        job = await service.get_job_by_id(job_id)
    except ResourceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Get raw logs (use async version to avoid blocking event loop)
    raw_logs = await service.read_job_logs_async(job.log_path)
    if not raw_logs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No logs available to normalize",
        )

    # Delete existing normalized logs (if any)
    from sqlalchemy import delete

    from app.models.normalized_log import NormalizedLogEntry

    await db.execute(
        delete(NormalizedLogEntry).where(NormalizedLogEntry.job_id == job_id)
    )
    await db.commit()

    # Normalize and store
    normalizer = LogNormalizerService()
    try:
        entries = await normalizer.normalize_and_store(db, job_id, raw_logs, agent_type)
        return {
            "success": True,
            "job_id": job_id,
            "entries_created": len(entries),
            "message": f"Successfully normalized {len(entries)} log entries",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to normalize logs: {str(e)}",
        )
