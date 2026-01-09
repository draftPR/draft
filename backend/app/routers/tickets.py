"""API router for Ticket endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.evidence import Evidence
from app.models.job import JobKind
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.schemas.evidence import EvidenceListResponse, EvidenceResponse
from app.schemas.job import JobCreateResponse, JobListResponse, JobResponse
from app.schemas.planner import (
    bucket_to_priority,
    BulkPriorityUpdateRequest,
    BulkPriorityUpdateResponse,
    BulkPriorityUpdateResult,
    priority_to_bucket,
)
from app.schemas.ticket import (
    BulkAcceptRequest,
    BulkAcceptResponse,
    BulkAcceptResult,
    TicketCreate,
    TicketDetailResponse,
    TicketResponse,
    TicketTransition,
)
from app.schemas.ticket_event import TicketEventListResponse, TicketEventResponse
from app.services.job_service import JobService
from app.services.ticket_service import TicketService
from app.state_machine import ActorType, EventType, TicketState

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
    "/accept",
    response_model=BulkAcceptResponse,
    summary="Bulk accept proposed tickets",
)
async def bulk_accept_tickets(
    data: BulkAcceptRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkAcceptResponse:
    """
    Bulk accept proposed tickets, transitioning them from 'proposed' to 'planned'.
    
    Validation rules:
    - All tickets must exist
    - All tickets must be in 'proposed' state
    - If goal_id is provided, all tickets must belong to that goal
    
    The operation is atomic: if any ticket fails validation, none are accepted.
    This prevents partial acceptance which causes UI confusion.
    
    If queue_first=true:
    - The FIRST ticket in the request order (ticket_ids[0]) will be queued
    - Request order is deterministic and matches UI selection order
    - Remaining tickets stay in 'planned' state (not auto-queued)
    - Job is created AFTER all transitions are committed
    - Returns queued_job_id and queued_ticket_id for traceability
    """
    from app.models.ticket import Ticket
    
    service = TicketService(db)
    job_service = JobService(db)
    rejected: list[BulkAcceptResult] = []
    
    # Phase 1: Pre-validation - fetch all tickets and validate
    # Preserve request order by using a list, not a dict
    tickets_to_accept: list[Ticket] = []
    
    for ticket_id in data.ticket_ids:
        try:
            ticket = await service.get_ticket_by_id(ticket_id)
        except Exception:
            rejected.append(BulkAcceptResult(
                ticket_id=ticket_id,
                success=False,
                error="Ticket not found",
            ))
            continue
        
        # Validate state
        if ticket.state != TicketState.PROPOSED.value:
            rejected.append(BulkAcceptResult(
                ticket_id=ticket_id,
                success=False,
                error=f"Ticket is in '{ticket.state}' state, not 'proposed'",
            ))
            continue
        
        # Validate goal ownership if goal_id provided
        if data.goal_id and ticket.goal_id != data.goal_id:
            rejected.append(BulkAcceptResult(
                ticket_id=ticket_id,
                success=False,
                error=f"Ticket belongs to goal '{ticket.goal_id}', not '{data.goal_id}'",
            ))
            continue
        
        tickets_to_accept.append(ticket)
    
    # If any tickets were rejected, don't accept any (atomic operation)
    if rejected:
        return BulkAcceptResponse(
            accepted_ids=[],
            rejected=rejected,
            accepted_count=0,
            failed_count=len(rejected),
            queued_job_id=None,
            queued_ticket_id=None,
        )
    
    # Phase 2: Accept all validated tickets within transaction
    # Note: SQLAlchemy async session auto-commits at the end of the request handler
    # unless we explicitly use db.begin() or db.rollback()
    accepted_ids: list[str] = []
    
    for ticket in tickets_to_accept:
        try:
            await service.transition_ticket(
                ticket_id=ticket.id,
                to_state=TicketState.PLANNED,
                actor_type=data.actor_type,
                actor_id=data.actor_id,
                reason=data.reason,
            )
            accepted_ids.append(ticket.id)
        except Exception as e:
            # This shouldn't happen after pre-validation, but handle it
            rejected.append(BulkAcceptResult(
                ticket_id=ticket.id,
                success=False,
                error=str(e),
            ))
            # Rollback will happen automatically on exception
            raise
    
    # Commit transitions before queueing job
    await db.commit()
    
    # Phase 3: Queue first ticket if requested (after commit)
    # This ensures the worker sees the updated ticket state
    queued_job_id: str | None = None
    queued_ticket_id: str | None = None
    
    if data.queue_first and accepted_ids:
        # Use first ticket in request order (deterministic)
        first_ticket_id = accepted_ids[0]
        try:
            job = await job_service.create_job(first_ticket_id, JobKind.EXECUTE)
            await db.commit()  # Commit job creation
            queued_job_id = job.id
            queued_ticket_id = first_ticket_id
        except Exception as e:
            # Don't fail the whole operation if queueing fails
            # Tickets are already accepted at this point
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to queue job for ticket {first_ticket_id}: {e}"
            )
    
    return BulkAcceptResponse(
        accepted_ids=accepted_ids,
        rejected=rejected,
        accepted_count=len(accepted_ids),
        failed_count=len(rejected),
        queued_job_id=queued_job_id,
        queued_ticket_id=queued_ticket_id,
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
    "/{ticket_id}/execute",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute a single ticket (run it now)",
)
async def execute_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    Execute a single ticket immediately.

    **Use this to run a specific ticket without using autopilot.**

    Valid ticket states for execution:
    - PLANNED: Normal execution
    - NEEDS_HUMAN: Re-run after human intervention
    - DONE: Re-run if changes were requested on revision

    The ticket will transition to EXECUTING when the job starts,
    then to VERIFYING or BLOCKED based on the outcome.

    For automated execution of all planned tickets, use `/planner/start`.
    """
    from app.state_machine import validate_transition
    
    ticket_service = TicketService(db)
    ticket = await ticket_service.get_ticket_by_id(ticket_id)
    
    # Validate ticket can transition to EXECUTING
    current_state = ticket.state_enum
    if not validate_transition(current_state, TicketState.EXECUTING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot execute ticket in '{current_state.value}' state. "
                   f"Ticket must be in PLANNED, NEEDS_HUMAN, or DONE state.",
        )
    
    job_service = JobService(db)
    job = await job_service.create_job(ticket_id, JobKind.EXECUTE)

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
    "/{ticket_id}/run",
    response_model=JobCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue an execute job for a ticket (alias for /execute)",
    deprecated=True,
)
async def run_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """
    **Deprecated: Use `/tickets/{ticket_id}/execute` instead.**

    Enqueue an execute job for a ticket.
    """
    return await execute_ticket(ticket_id, db)


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


@router.post(
    "/bulk-update-priority",
    response_model=BulkPriorityUpdateResponse,
    summary="Bulk update ticket priorities",
)
async def bulk_update_priority(
    request: BulkPriorityUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkPriorityUpdateResponse:
    """
    Bulk update priorities for multiple tickets.

    This endpoint is designed to work with the reflection feature:
    1. Call `POST /goals/{id}/reflect-on-tickets` to get suggested changes
    2. Review the suggestions in the UI
    3. Call this endpoint with selected changes to apply them

    **Authorization:**
    - `board_id` is REQUIRED - all operations are scoped to this board
    - All tickets must belong to both the specified `board_id` AND `goal_id`

    **Safety:**
    - P0 assignments require `allow_p0: true` flag
    - Max 3 P0 assignments per request (server-enforced)
    - All changes are logged with PRIORITY_BULK_UPDATED event

    **Request:**
    ```json
    {
      "board_id": "uuid",
      "goal_id": "uuid",
      "allow_p0": true,
      "updates": [
        {"ticket_id": "uuid", "priority_bucket": "P1"},
        {"ticket_id": "uuid", "priority_bucket": "P0"}
      ]
    }
    ```

    **Priority Buckets:**
    - P0 → 90 (Critical) - requires allow_p0=true
    - P1 → 70 (High)
    - P2 → 50 (Medium)
    - P3 → 30 (Low)
    """
    from app.schemas.planner import MAX_P0_PER_REQUEST, PriorityBucket
    from app.services.board_service import BoardService
    from fastapi.responses import JSONResponse
    
    # AUTHORIZATION: Verify board exists
    board_service = BoardService(db)
    try:
        await board_service.get_board_by_id(request.board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    # Verify goal belongs to board
    try:
        await board_service.verify_goal_in_board(request.goal_id, request.board_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    results: list[BulkPriorityUpdateResult] = []
    updated_count = 0
    failed_count = 0
    
    # Identify P0 assignments
    p0_updates = [u for u in request.updates if u.priority_bucket == PriorityBucket.P0]
    p0_count = len(p0_updates)
    p0_ticket_ids = [u.ticket_id for u in p0_updates]
    
    # P0 safety checks with structured error
    if p0_count > 0:
        if not request.allow_p0:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": f"P0 assignments require allow_p0=true flag.",
                    "error_type": "p0_flag_required",
                    "p0_count": p0_count,
                    "p0_ticket_ids": p0_ticket_ids,
                    "max_p0_per_request": MAX_P0_PER_REQUEST,
                    "resolution": "Add allow_p0: true to your request body to confirm P0 assignments.",
                },
            )
        if p0_count > MAX_P0_PER_REQUEST:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": f"Max {MAX_P0_PER_REQUEST} P0 assignments per request.",
                    "error_type": "p0_limit_exceeded",
                    "p0_count": p0_count,
                    "p0_ticket_ids": p0_ticket_ids,
                    "max_p0_per_request": MAX_P0_PER_REQUEST,
                    "resolution": f"Split into multiple requests with at most {MAX_P0_PER_REQUEST} P0 assignments each.",
                },
            )
    
    # Track before/after for audit logging
    changes_log = []

    for update in request.updates:
        # AUTHORIZATION: Verify ticket belongs to board AND goal
        try:
            ticket = await board_service.verify_ticket_in_board(
                update.ticket_id, request.board_id
            )
        except ValueError:
            results.append(
                BulkPriorityUpdateResult(
                    ticket_id=update.ticket_id,
                    success=False,
                    error="Ticket not found or does not belong to board",
                )
            )
            failed_count += 1
            continue

        # Security check: verify ticket belongs to the specified goal
        if ticket.goal_id != request.goal_id:
            results.append(
                BulkPriorityUpdateResult(
                    ticket_id=update.ticket_id,
                    success=False,
                    error="Ticket does not belong to specified goal",
                )
            )
            failed_count += 1
            continue

        # Record before state for audit
        old_priority = ticket.priority
        old_bucket = priority_to_bucket(old_priority) if old_priority else PriorityBucket.P2

        # Update priority
        new_priority = bucket_to_priority(update.priority_bucket)
        ticket.priority = new_priority
        
        changes_log.append({
            "ticket_id": ticket.id,
            "ticket_title": ticket.title,
            "old_bucket": old_bucket.value,
            "new_bucket": update.priority_bucket.value,
            "old_priority": old_priority,
            "new_priority": new_priority,
        })

        results.append(
            BulkPriorityUpdateResult(
                ticket_id=update.ticket_id,
                success=True,
                new_priority=new_priority,
                new_bucket=update.priority_bucket,
            )
        )
        updated_count += 1

    # Create audit event for all changes
    if updated_count > 0 and changes_log:
        # Count direction of changes
        up_count = sum(1 for c in changes_log if c["new_priority"] > (c["old_priority"] or 0))
        down_count = sum(1 for c in changes_log if c["new_priority"] < (c["old_priority"] or 0))
        to_p0_count = sum(1 for c in changes_log if c["new_bucket"] == "P0" and c["old_bucket"] != "P0")
        
        # Log the bulk update event (one per goal, includes all ticket changes)
        # Get first ticket's ID for the event
        first_ticket_id = changes_log[0]["ticket_id"]
        
        event = TicketEvent(
            ticket_id=first_ticket_id,
            event_type="priority_bulk_updated",
            from_state=None,
            to_state=None,
            actor_type=ActorType.HUMAN.value,
            actor_id="bulk_priority_update",
            reason=f"Bulk priority update: {updated_count} tickets ({up_count} up, {down_count} down, {to_p0_count} to P0)",
            payload_json=json.dumps({
                "goal_id": request.goal_id,
                "total_updated": updated_count,
                "up_count": up_count,
                "down_count": down_count,
                "to_p0_count": to_p0_count,
                "allow_p0": request.allow_p0,
                "changes": changes_log,
            }),
        )
        db.add(event)

    await db.commit()

    return BulkPriorityUpdateResponse(
        updated=results,
        updated_count=updated_count,
        failed_count=failed_count,
    )
