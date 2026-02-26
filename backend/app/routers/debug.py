"""API router for Debug endpoints - live logs and system status."""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.evidence import Evidence
from app.models.job import Job, JobStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.state_machine import TicketState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])

# In-memory log buffer for orchestrator events (circular buffer)
MAX_LOG_ENTRIES = 500
_orchestrator_logs: deque[dict] = deque(maxlen=MAX_LOG_ENTRIES)


def add_orchestrator_log(level: str, message: str, data: dict | None = None) -> None:
    """Add a log entry to the orchestrator log buffer."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "message": message,
        "data": data or {},
    }
    _orchestrator_logs.append(entry)


class OrchestratorLogEntry(BaseModel):
    """A single orchestrator log entry."""
    timestamp: str
    level: str
    message: str
    data: dict


class OrchestratorLogsResponse(BaseModel):
    """Response containing orchestrator logs."""
    logs: list[OrchestratorLogEntry]
    total: int


class AgentLogEntry(BaseModel):
    """A single agent log entry with context."""
    timestamp: str
    job_id: str
    ticket_id: str
    ticket_title: str
    kind: str
    content: str


class AgentLogsResponse(BaseModel):
    """Response containing agent logs."""
    logs: list[AgentLogEntry]
    job_id: str | None
    ticket_title: str | None


class RunningJobInfo(BaseModel):
    """Information about a running job."""
    job_id: str
    ticket_id: str
    ticket_title: str
    kind: str
    started_at: str | None
    log_preview: str | None


class SystemStatusResponse(BaseModel):
    """Live system status for debug panel."""
    timestamp: str
    running_jobs: list[RunningJobInfo]
    queued_count: int
    tickets_by_state: dict[str, int]
    recent_events_count: int


@router.get(
    "/orchestrator/logs",
    response_model=OrchestratorLogsResponse,
    summary="Get orchestrator logs from in-memory buffer",
)
async def get_orchestrator_logs(
    limit: int = Query(default=100, le=500, description="Number of log entries to return"),
    since: str | None = Query(default=None, description="Only return logs after this ISO timestamp"),
) -> OrchestratorLogsResponse:
    """
    Get recent orchestrator logs from the in-memory buffer.

    These logs capture planner decisions, ticket state transitions,
    and other orchestrator-level events.
    """
    logs = list(_orchestrator_logs)

    # Filter by timestamp if provided
    if since:
        logs = [l for l in logs if l["timestamp"] > since]

    # Return most recent entries (buffer stores oldest to newest)
    logs = logs[-limit:]

    return OrchestratorLogsResponse(
        logs=[OrchestratorLogEntry(**l) for l in logs],
        total=len(_orchestrator_logs),
    )


@router.get(
    "/orchestrator/stream",
    summary="Stream orchestrator logs via Server-Sent Events",
)
async def stream_orchestrator_logs() -> StreamingResponse:
    """
    Stream orchestrator logs in real-time using Server-Sent Events (SSE).

    Connect to this endpoint to receive live log updates as they happen.
    Each event is a JSON object with timestamp, level, message, and data.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        len(_orchestrator_logs)
        last_timestamp = ""

        # Send initial logs
        for log in list(_orchestrator_logs)[-20:]:  # Last 20 entries
            import json
            yield f"data: {json.dumps(log)}\n\n"
            last_timestamp = log["timestamp"]

        # Stream new logs
        while True:
            await asyncio.sleep(0.5)  # Poll every 500ms

            current_logs = list(_orchestrator_logs)
            if not current_logs:
                continue

            # Find new logs since last check
            new_logs = [l for l in current_logs if l["timestamp"] > last_timestamp]

            for log in new_logs:
                import json
                yield f"data: {json.dumps(log)}\n\n"
                last_timestamp = log["timestamp"]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/agent/logs/{job_id}",
    response_model=AgentLogsResponse,
    summary="Get agent output for a specific job",
)
async def get_agent_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgentLogsResponse:
    """
    Get the agent's stdout/stderr for a specific job.

    This returns the actual output from the executor (cursor-agent, etc.)
    showing what the agent did and why.
    """
    # Get job with ticket
    result = await db.execute(
        select(Job)
        .options(selectinload(Job.ticket))
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        return AgentLogsResponse(logs=[], job_id=job_id, ticket_title=None)

    # Get evidence for this job (executor stdout)
    evidence_result = await db.execute(
        select(Evidence)
        .where(Evidence.job_id == job_id)
        .order_by(Evidence.created_at)
    )
    evidences = evidence_result.scalars().all()

    logs = []
    for ev in evidences:
        # Try to get stdout content
        content = ""
        if ev.stdout_path:
            try:
                from pathlib import Path
                stdout_path = Path(ev.stdout_path)
                if stdout_path.exists():
                    content = stdout_path.read_text()[:10000]  # Limit size
            except Exception:
                content = f"[Error reading stdout from {ev.stdout_path}]"

        if content:
            logs.append(AgentLogEntry(
                timestamp=ev.created_at.isoformat() if ev.created_at else "",
                job_id=job_id,
                ticket_id=job.ticket_id,
                ticket_title=job.ticket.title if job.ticket else "Unknown",
                kind=ev.kind,
                content=content,
            ))

    return AgentLogsResponse(
        logs=logs,
        job_id=job_id,
        ticket_title=job.ticket.title if job.ticket else None,
    )


@router.get(
    "/agent/stream/{job_id}",
    summary="Stream agent logs for a running job",
)
async def stream_agent_logs(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream agent logs in real-time for a running job.

    Tails the job's log file and streams updates as they happen.
    """
    from pathlib import Path

    # Get job to find log path
    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()

    async def event_generator() -> AsyncGenerator[str, None]:
        import json

        if not job or not job.log_path:
            yield f"data: {json.dumps({'error': 'No log file found'})}\n\n"
            return

        log_path = Path(job.log_path)
        last_size = 0

        while True:
            try:
                if log_path.exists():
                    current_size = log_path.stat().st_size

                    if current_size > last_size:
                        with open(log_path) as f:
                            f.seek(last_size)
                            new_content = f.read()
                            if new_content:
                                yield f"data: {json.dumps({'content': new_content})}\n\n"
                        last_size = current_size

                # Check if job is still running
                async with db.begin():
                    job_check = await db.execute(
                        select(Job.status).where(Job.id == job_id)
                    )
                    status = job_check.scalar_one_or_none()
                    if status and status not in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
                        yield f"data: {json.dumps({'status': 'completed', 'final_status': status})}\n\n"
                        break

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get live system status for debug panel",
)
async def get_system_status(
    db: AsyncSession = Depends(get_db),
) -> SystemStatusResponse:
    """
    Get comprehensive system status for the debug panel.

    Returns:
    - Running jobs with log previews
    - Queued job count
    - Ticket counts by state
    - Recent event count
    """
    # Get running jobs with ticket info
    running_result = await db.execute(
        select(Job)
        .options(selectinload(Job.ticket))
        .where(Job.status == JobStatus.RUNNING.value)
        .order_by(Job.started_at)
    )
    running_jobs = running_result.scalars().all()

    running_info = []
    for job in running_jobs:
        # Try to get last few lines of log
        log_preview = None
        if job.log_path:
            try:
                from pathlib import Path
                log_path = Path(job.log_path)
                if log_path.exists():
                    content = log_path.read_text()
                    lines = content.strip().split('\n')
                    log_preview = '\n'.join(lines[-5:])  # Last 5 lines
            except Exception:
                pass

        running_info.append(RunningJobInfo(
            job_id=job.id,
            ticket_id=job.ticket_id,
            ticket_title=job.ticket.title if job.ticket else "Unknown",
            kind=job.kind,
            started_at=job.started_at.isoformat() if job.started_at else None,
            log_preview=log_preview,
        ))

    # Count queued jobs
    queued_result = await db.execute(
        select(Job).where(Job.status == JobStatus.QUEUED.value)
    )
    queued_count = len(queued_result.scalars().all())

    # Count tickets by state
    tickets_by_state = {}
    for state in TicketState:
        result = await db.execute(
            select(Ticket).where(Ticket.state == state.value)
        )
        count = len(result.scalars().all())
        if count > 0:
            tickets_by_state[state.value] = count

    # Count recent events (last hour)
    from datetime import timedelta
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    events_result = await db.execute(
        select(TicketEvent).where(TicketEvent.created_at >= one_hour_ago)
    )
    recent_events_count = len(events_result.scalars().all())

    return SystemStatusResponse(
        timestamp=datetime.now(UTC).isoformat(),
        running_jobs=running_info,
        queued_count=queued_count,
        tickets_by_state=tickets_by_state,
        recent_events_count=recent_events_count,
    )


class ResetResponse(BaseModel):
    """Response from reset operation."""
    tickets_deleted: int
    goals_deleted: int
    jobs_deleted: int
    events_deleted: int
    message: str


@router.post(
    "/reset",
    response_model=ResetResponse,
    summary="[DEV ONLY] Delete ALL data - nuclear reset",
)
async def reset_all_data(
    confirm: str = Query(..., description="Must be 'yes-delete-everything' to confirm"),
    db: AsyncSession = Depends(get_db),
) -> ResetResponse:
    """
    **DANGER:** Delete ALL tickets, goals, jobs, events, evidence, etc.

    This is a nuclear option for development/testing. Use with caution.

    Requires `confirm=yes-delete-everything` query parameter.
    """
    if confirm != "yes-delete-everything":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Must provide confirm=yes-delete-everything to proceed"
        )

    from app.models.analysis_cache import AnalysisCache
    from app.models.goal import Goal
    from app.models.planner_lock import PlannerLock
    from app.models.review_comment import ReviewComment
    from app.models.review_summary import ReviewSummary
    from app.models.revision import Revision
    from app.models.workspace import Workspace

    # Count before deletion
    tickets_count = len((await db.execute(select(Ticket))).scalars().all())
    goals_count = len((await db.execute(select(Goal))).scalars().all())
    jobs_count = len((await db.execute(select(Job))).scalars().all())
    events_count = len((await db.execute(select(TicketEvent))).scalars().all())

    # Delete in correct order (respecting foreign keys)
    # 1. Review comments and summaries
    await db.execute(select(ReviewComment).execution_options(synchronize_session=False))
    for rc in (await db.execute(select(ReviewComment))).scalars().all():
        await db.delete(rc)

    for rs in (await db.execute(select(ReviewSummary))).scalars().all():
        await db.delete(rs)

    # 2. Revisions
    for rev in (await db.execute(select(Revision))).scalars().all():
        await db.delete(rev)

    # 3. Evidence
    for ev in (await db.execute(select(Evidence))).scalars().all():
        await db.delete(ev)

    # 4. Jobs
    for job in (await db.execute(select(Job))).scalars().all():
        await db.delete(job)

    # 5. Ticket events
    for event in (await db.execute(select(TicketEvent))).scalars().all():
        await db.delete(event)

    # 6. Tickets
    for ticket in (await db.execute(select(Ticket))).scalars().all():
        await db.delete(ticket)

    # 7. Workspaces
    for ws in (await db.execute(select(Workspace))).scalars().all():
        await db.delete(ws)

    # 8. Goals
    for goal in (await db.execute(select(Goal))).scalars().all():
        await db.delete(goal)

    # 9. Planner locks
    for lock in (await db.execute(select(PlannerLock))).scalars().all():
        await db.delete(lock)

    # 10. Analysis cache
    for cache in (await db.execute(select(AnalysisCache))).scalars().all():
        await db.delete(cache)

    await db.commit()

    # Clear in-memory logs too
    _orchestrator_logs.clear()

    return ResetResponse(
        tickets_deleted=tickets_count,
        goals_deleted=goals_count,
        jobs_deleted=jobs_count,
        events_deleted=events_count,
        message="All data deleted successfully",
    )


@router.get(
    "/events/recent",
    summary="Get recent ticket events for activity feed",
)
async def get_recent_events(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Get recent ticket events for the activity feed.

    Returns events ordered by most recent first.
    """
    result = await db.execute(
        select(TicketEvent)
        .options(selectinload(TicketEvent.ticket))
        .order_by(desc(TicketEvent.created_at))
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        {
            "id": ev.id,
            "ticket_id": ev.ticket_id,
            "ticket_title": ev.ticket.title if ev.ticket else None,
            "event_type": ev.event_type,
            "actor_type": ev.actor_type,
            "actor_id": ev.actor_id,
            "payload": ev.get_payload(),
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in events
    ]

