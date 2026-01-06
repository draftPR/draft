"""API router for Ticket endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.evidence import Evidence
from app.models.job import JobKind
from app.schemas.evidence import EvidenceListResponse, EvidenceResponse
from app.schemas.job import JobCreateResponse, JobListResponse, JobResponse
from app.schemas.ticket import (
    TicketCreate,
    TicketDetailResponse,
    TicketResponse,
    TicketTransition,
)
from app.schemas.ticket_event import TicketEventListResponse, TicketEventResponse
from app.services.job_service import JobService
from app.services.ticket_service import TicketService
from app.state_machine import EventType

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ticket",
)
async def create_ticket(
    data: TicketCreate,
    db: AsyncSession = Depends(get_db),
) -> TicketResponse:
    """
    Create a new ticket linked to a goal.
    The ticket will start in the 'proposed' state.
    """
    service = TicketService(db)
    ticket = await service.create_ticket(data)
    return TicketResponse.model_validate(ticket)


@router.get(
    "/{ticket_id}",
    response_model=TicketDetailResponse,
    summary="Get a ticket by ID",
)
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> TicketDetailResponse:
    """Get a ticket by its ID with full context."""
    service = TicketService(db)
    ticket = await service.get_ticket_by_id(ticket_id)

    return TicketDetailResponse(
        id=ticket.id,
        goal_id=ticket.goal_id,
        goal_title=ticket.goal.title if ticket.goal else None,
        goal_description=ticket.goal.description if ticket.goal else None,
        title=ticket.title,
        description=ticket.description,
        state=ticket.state_enum,
        state_display=TicketDetailResponse.get_state_display(ticket.state_enum),
        priority=ticket.priority,
        priority_label=TicketDetailResponse.get_priority_label(ticket.priority),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


@router.post(
    "/{ticket_id}/transition",
    response_model=TicketResponse,
    summary="Transition a ticket to a new state",
)
async def transition_ticket(
    ticket_id: str,
    data: TicketTransition,
    db: AsyncSession = Depends(get_db),
) -> TicketResponse:
    """
    Transition a ticket to a new state.

    The transition must be valid according to the state machine rules.
    An event will be recorded for this transition.
    """
    service = TicketService(db)
    ticket = await service.transition_ticket(
        ticket_id=ticket_id,
        to_state=data.to_state,
        actor_type=data.actor_type,
        actor_id=data.actor_id,
        reason=data.reason,
    )
    return TicketResponse.model_validate(ticket)


@router.get(
    "/{ticket_id}/events",
    response_model=TicketEventListResponse,
    summary="Get all events for a ticket",
)
async def get_ticket_events(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> TicketEventListResponse:
    """Get the event history for a ticket."""
    service = TicketService(db)
    events = await service.get_ticket_events(ticket_id)

    # Transform events to response schema
    event_responses = []
    for event in events:
        event_responses.append(
            TicketEventResponse(
                id=event.id,
                ticket_id=event.ticket_id,
                event_type=EventType(event.event_type),
                from_state=event.from_state,
                to_state=event.to_state,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                reason=event.reason,
                payload=event.get_payload(),
                created_at=event.created_at,
            )
        )

    return TicketEventListResponse(
        events=event_responses,
        total=len(event_responses),
    )


@router.post(
    "/{ticket_id}/run",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue an execute job for a ticket",
)
async def run_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    Enqueue an execute job for a ticket.

    Creates a new Job record with kind='execute' and status='queued',
    then dispatches a Celery task to execute the ticket.
    """
    service = JobService(db)
    job = await service.create_job(ticket_id, JobKind.EXECUTE)

    return JobCreateResponse(
        id=job.id,
        ticket_id=job.ticket_id,
        kind=job.kind_enum,
        status=job.status_enum,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        exit_code=job.exit_code,
        log_path=job.log_path,
        celery_task_id=job.celery_task_id,
    )


@router.post(
    "/{ticket_id}/verify",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a verify job for a ticket",
)
async def verify_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    Enqueue a verify job for a ticket.

    Creates a new Job record with kind='verify' and status='queued',
    then dispatches a Celery task to verify the ticket.
    """
    service = JobService(db)
    job = await service.create_job(ticket_id, JobKind.VERIFY)

    return JobCreateResponse(
        id=job.id,
        ticket_id=job.ticket_id,
        kind=job.kind_enum,
        status=job.status_enum,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        exit_code=job.exit_code,
        log_path=job.log_path,
        celery_task_id=job.celery_task_id,
    )


@router.post(
    "/{ticket_id}/resume",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Resume an interactive ticket after human completion",
)
async def resume_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    Resume an interactive ticket after human completion.

    Use this endpoint when:
    1. A ticket was transitioned to 'needs_human' by an interactive executor (Cursor)
    2. The human has made their changes in the worktree
    3. The human wants to continue the workflow

    This endpoint:
    1. Creates a 'resume' job that captures the git diff as evidence
    2. Transitions the ticket to 'verifying' state
    3. Queues a verification job

    The resume job will fail if the ticket is not in 'needs_human' state.
    """
    service = JobService(db)
    job = await service.create_job(ticket_id, JobKind.RESUME)

    return JobCreateResponse(
        id=job.id,
        ticket_id=job.ticket_id,
        kind=job.kind_enum,
        status=job.status_enum,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        exit_code=job.exit_code,
        log_path=job.log_path,
        celery_task_id=job.celery_task_id,
    )


@router.get(
    "/{ticket_id}/jobs",
    response_model=JobListResponse,
    summary="Get all jobs for a ticket",
)
async def get_ticket_jobs(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """Get all jobs associated with a ticket, ordered by creation time descending."""
    service = JobService(db)
    jobs = await service.get_jobs_for_ticket(ticket_id)

    job_responses = [
        JobResponse(
            id=job.id,
            ticket_id=job.ticket_id,
            kind=job.kind_enum,
            status=job.status_enum,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            exit_code=job.exit_code,
            log_path=job.log_path,
        )
        for job in jobs
    ]

    return JobListResponse(
        jobs=job_responses,
        total=len(job_responses),
    )


@router.get(
    "/{ticket_id}/evidence",
    response_model=EvidenceListResponse,
    summary="Get all verification evidence for a ticket",
)
async def get_ticket_evidence(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvidenceListResponse:
    """
    Get all verification evidence for a ticket.

    Returns evidence records from all verification jobs, ordered by creation time descending.
    """
    # First verify the ticket exists
    service = TicketService(db)
    await service.get_ticket_by_id(ticket_id)

    # Get all evidence for the ticket
    result = await db.execute(
        select(Evidence)
        .where(Evidence.ticket_id == ticket_id)
        .order_by(Evidence.created_at.desc())
    )
    evidence_list = list(result.scalars().all())

    evidence_responses = [
        EvidenceResponse(
            id=e.id,
            ticket_id=e.ticket_id,
            job_id=e.job_id,
            kind=e.kind_enum,
            command=e.command,
            exit_code=e.exit_code,
            stdout_path=e.stdout_path,
            stderr_path=e.stderr_path,
            created_at=e.created_at,
            succeeded=e.succeeded,
        )
        for e in evidence_list
    ]

    return EvidenceListResponse(
        evidence=evidence_responses,
        total=len(evidence_responses),
    )
