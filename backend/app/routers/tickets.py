"""API router for Ticket endpoints."""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.evidence import Evidence
from app.models.job import JobKind
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.schemas.common import PaginatedResponse
from app.schemas.evidence import EvidenceListResponse, EvidenceResponse
from app.schemas.job import JobCreateResponse, JobListResponse, JobResponse
from app.schemas.planner import (
    BulkPriorityUpdateRequest,
    BulkPriorityUpdateResponse,
    BulkPriorityUpdateResult,
    bucket_to_priority,
    priority_to_bucket,
)
from app.schemas.ticket import (
    BulkAcceptRequest,
    BulkAcceptResponse,
    BulkAcceptResult,
    BulkTransitionRequest,
    BulkTransitionResponse,
    BulkTransitionResult,
    TicketCreate,
    TicketDetailResponse,
    TicketReorderRequest,
    TicketResponse,
    TicketTransition,
    TicketUpdate,
)
from app.schemas.ticket_event import TicketEventListResponse, TicketEventResponse
from app.services.job_service import JobService
from app.services.ticket_service import TicketService
from app.state_machine import ActorType, EventType, TicketState, validate_transition
from app.websocket.manager import manager as connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


async def _broadcast_board_invalidate(board_id: str | None, reason: str = "ticket_mutation") -> None:
    """Broadcast a board invalidation message via WebSocket if board_id is available."""
    if board_id:
        await connection_manager.broadcast(
            f"board:{board_id}",
            {"type": "invalidate", "reason": reason},
        )


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
    "",
    response_model=PaginatedResponse[TicketResponse],
    summary="List tickets with optional filtering and pagination",
)
async def list_tickets(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    state: TicketState | None = Query(None, description="Filter by ticket state"),
    priority_min: int | None = Query(
        None, ge=0, le=100, description="Minimum priority"
    ),
    priority_max: int | None = Query(
        None, ge=0, le=100, description="Maximum priority"
    ),
    goal_id: str | None = Query(None, description="Filter by goal ID"),
    board_id: str | None = Query(None, description="Filter by board ID"),
    q: str | None = Query(
        None,
        min_length=1,
        max_length=200,
        description="Text search on title/description",
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TicketResponse]:
    """
    List tickets with optional filtering and pagination.

    **Filters:**
    - `state`: Filter by ticket state (e.g., planned, executing)
    - `priority_min` / `priority_max`: Filter by priority range
    - `goal_id`: Filter by parent goal
    - `board_id`: Filter by board
    - `q`: Full-text search on title and description

    **Pagination:**
    - `page`: Page number (1-based, default 1)
    - `limit`: Items per page (default 50, max 200)
    """
    query = select(Ticket).options(selectinload(Ticket.blocked_by))
    count_query = select(func.count(Ticket.id))

    # Apply filters
    if state is not None:
        query = query.where(Ticket.state == state.value)
        count_query = count_query.where(Ticket.state == state.value)
    if priority_min is not None:
        query = query.where(Ticket.priority >= priority_min)
        count_query = count_query.where(Ticket.priority >= priority_min)
    if priority_max is not None:
        query = query.where(Ticket.priority <= priority_max)
        count_query = count_query.where(Ticket.priority <= priority_max)
    if goal_id is not None:
        query = query.where(Ticket.goal_id == goal_id)
        count_query = count_query.where(Ticket.goal_id == goal_id)
    if board_id is not None:
        query = query.where(Ticket.board_id == board_id)
        count_query = count_query.where(Ticket.board_id == board_id)
    if q is not None:
        search_pattern = f"%{q}%"
        search_filter = or_(
            Ticket.title.ilike(search_pattern),
            Ticket.description.ilike(search_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering and pagination
    offset = (page - 1) * limit
    query = query.order_by(
        Ticket.priority.desc().nulls_last(),
        Ticket.created_at.desc(),
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    tickets = result.scalars().all()

    items = []
    for ticket in tickets:
        ticket_data = TicketResponse.model_validate(ticket).model_dump()
        if ticket.blocked_by_ticket_id and ticket.blocked_by:
            ticket_data["blocked_by_ticket_title"] = ticket.blocked_by.title
        items.append(TicketResponse(**ticket_data))

    return PaginatedResponse[TicketResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


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
    from app.state_machine import TicketState as TS

    service = TicketService(db)
    ticket = await service.get_ticket_by_id(ticket_id)

    # Determine if ticket is blocked by an incomplete dependency
    is_blocked = False
    blocked_by_title = None
    if ticket.blocked_by_ticket_id:
        if ticket.blocked_by:
            blocked_by_title = ticket.blocked_by.title
            is_blocked = ticket.blocked_by.state != TS.DONE.value
        else:
            is_blocked = True  # Assume blocked if relationship not loaded

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
        blocked_by_ticket_id=ticket.blocked_by_ticket_id,
        blocked_by_ticket_title=blocked_by_title,
        is_blocked=is_blocked,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a ticket",
)
async def delete_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a ticket and all its associated data.

    This will cascade delete:
    - All jobs for this ticket
    - All revisions and their review comments/summaries
    - All ticket events
    - The workspace and worktree (best effort)
    - All evidence files

    **WARNING:** This action cannot be undone!
    """
    from sqlalchemy import delete as sql_delete

    service = TicketService(db)

    # Verify ticket exists and get board_id for broadcast
    ticket = await service.get_ticket_by_id(ticket_id)
    board_id = ticket.board_id

    # Clean up workspace (best effort, don't block deletion if it fails)
    try:
        await service._cleanup_workspace_async(ticket_id)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to cleanup workspace for ticket {ticket_id}: {e}")

    # Delete the ticket (cascade will handle related records)
    await db.execute(sql_delete(Ticket).where(Ticket.id == ticket_id))

    # Broadcast board invalidation
    await _broadcast_board_invalidate(board_id, reason="ticket_deleted")


@router.patch(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Update a ticket",
)
async def update_ticket(
    ticket_id: str,
    data: TicketUpdate,
    db: AsyncSession = Depends(get_db),
) -> TicketResponse:
    """Update a ticket's title, description, or priority."""
    service = TicketService(db)
    ticket = await service.get_ticket_by_id(ticket_id)

    if "title" in data.model_fields_set:
        ticket.title = data.title
    if "description" in data.model_fields_set:
        ticket.description = data.description
    if "priority" in data.model_fields_set:
        ticket.priority = data.priority

    await db.flush()
    await db.refresh(ticket)

    # Broadcast board invalidation
    await _broadcast_board_invalidate(ticket.board_id, reason="ticket_updated")

    return TicketResponse(
        id=ticket.id,
        goal_id=ticket.goal_id,
        title=ticket.title,
        description=ticket.description,
        state=ticket.state,
        priority=ticket.priority,
        blocked_by_ticket_id=ticket.blocked_by_ticket_id,
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
            rejected.append(
                BulkAcceptResult(
                    ticket_id=ticket_id,
                    success=False,
                    error="Ticket not found",
                )
            )
            continue

        # Validate state
        if ticket.state != TicketState.PROPOSED.value:
            rejected.append(
                BulkAcceptResult(
                    ticket_id=ticket_id,
                    success=False,
                    error=f"Ticket is in '{ticket.state}' state, not 'proposed'",
                )
            )
            continue

        # Validate goal ownership if goal_id provided
        if data.goal_id and ticket.goal_id != data.goal_id:
            rejected.append(
                BulkAcceptResult(
                    ticket_id=ticket_id,
                    success=False,
                    error=f"Ticket belongs to goal '{ticket.goal_id}', not '{data.goal_id}'",
                )
            )
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
            rejected.append(
                BulkAcceptResult(
                    ticket_id=ticket.id,
                    success=False,
                    error=str(e),
                )
            )
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
    "/bulk-transition",
    response_model=BulkTransitionResponse,
    summary="Bulk transition multiple tickets to a new state",
)
async def bulk_transition_tickets(
    data: BulkTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkTransitionResponse:
    """
    Transition multiple tickets to a new state in a single request.

    Each ticket is validated independently against the state machine.
    Tickets that fail validation are skipped (partial success is allowed).

    **Use cases:**
    - Bulk abandon tickets
    - Bulk move tickets back to planned
    - Bulk mark tickets as done
    """
    service = TicketService(db)
    results: list[BulkTransitionResult] = []
    transitioned_count = 0
    failed_count = 0

    for ticket_id in data.ticket_ids:
        try:
            ticket = await service.get_ticket_by_id(ticket_id)
            from_state = TicketState(ticket.state)

            # Validate transition
            if not validate_transition(from_state, data.target_state):
                results.append(
                    BulkTransitionResult(
                        ticket_id=ticket_id,
                        success=False,
                        error=(
                            f"Invalid transition from '{from_state.value}' "
                            f"to '{data.target_state.value}'"
                        ),
                        from_state=from_state.value,
                        to_state=data.target_state.value,
                    )
                )
                failed_count += 1
                continue

            await service.transition_ticket(
                ticket_id=ticket_id,
                to_state=data.target_state,
                actor_type=data.actor_type,
                actor_id=data.actor_id,
                reason=data.reason,
            )
            results.append(
                BulkTransitionResult(
                    ticket_id=ticket_id,
                    success=True,
                    from_state=from_state.value,
                    to_state=data.target_state.value,
                )
            )
            transitioned_count += 1
        except Exception as e:
            results.append(
                BulkTransitionResult(
                    ticket_id=ticket_id,
                    success=False,
                    error=str(e),
                )
            )
            failed_count += 1

    # Commit all successful transitions
    if transitioned_count > 0:
        await db.commit()

    return BulkTransitionResponse(
        results=results,
        transitioned_count=transitioned_count,
        failed_count=failed_count,
    )


@router.patch(
    "/reorder",
    response_model=TicketResponse,
    summary="Reorder a ticket within a state column",
)
async def reorder_ticket(
    data: TicketReorderRequest,
    db: AsyncSession = Depends(get_db),
) -> TicketResponse:
    """
    Reorder a ticket within its state column by updating sort_order.

    Moves the ticket to `new_index` (0-based) within the specified
    `column_state`. Other tickets in the column are re-indexed to
    maintain a contiguous order.

    **Note:** The ticket must already be in the specified column_state.
    """
    # Verify the ticket exists and is in the correct state
    service = TicketService(db)
    ticket = await service.get_ticket_by_id(data.ticket_id)

    if ticket.state != data.column_state.value:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ticket is in '{ticket.state}' state, "
                f"not '{data.column_state.value}'"
            ),
        )

    # Get all tickets in the same column, ordered by sort_order
    column_query = (
        select(Ticket)
        .where(Ticket.state == data.column_state.value)
        .order_by(
            Ticket.sort_order.asc().nulls_last(),
            Ticket.priority.desc().nulls_last(),
            Ticket.created_at.desc(),
        )
    )
    # Scope to same board if ticket has board_id
    if ticket.board_id:
        column_query = column_query.where(
            Ticket.board_id == ticket.board_id
        )

    result = await db.execute(column_query)
    column_tickets = list(result.scalars().all())

    # Remove the target ticket from the list
    column_tickets = [t for t in column_tickets if t.id != data.ticket_id]

    # Clamp new_index to valid range
    new_index = min(data.new_index, len(column_tickets))

    # Insert at new position
    column_tickets.insert(new_index, ticket)

    # Re-assign sort_order for all tickets in the column
    for idx, t in enumerate(column_tickets):
        t.sort_order = idx

    await db.flush()
    await db.refresh(ticket)

    # Broadcast board invalidation
    await _broadcast_board_invalidate(
        ticket.board_id, reason="ticket_reordered"
    )

    return TicketResponse.model_validate(ticket)


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

    # Broadcast board invalidation
    await _broadcast_board_invalidate(ticket.board_id, reason="ticket_transition")

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
    executor_profile: str | None = None,
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

    Pass `executor_profile` query param to use a named profile from
    smartkanban.yaml (e.g., `?executor_profile=fast`).

    For automated execution of all planned tickets, use `/planner/start`.
    """
    from app.state_machine import validate_transition

    # Validate executor profile if specified
    if executor_profile:
        from app.services.config_service import ConfigService

        config_service = ConfigService()
        profile = config_service.get_executor_profile(executor_profile)
        if not profile:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown executor profile: '{executor_profile}'. "
                f"Available: {list(config_service.get_executor_profiles().keys())}",
            )

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

    # Check dependency: ticket cannot execute if blocked by an incomplete ticket
    if ticket.is_blocked_by_dependency:
        blocker_title = ticket.blocked_by.title if ticket.blocked_by else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Cannot execute: ticket is blocked by '{blocker_title}' "
            f"(id: {ticket.blocked_by_ticket_id}) which is not yet done.",
        )

    # Transition ticket to EXECUTING immediately so the board reflects it
    # before the Celery worker picks up the job. This prevents the "bounce"
    # where optimistic UI update snaps back on the next board refresh.
    if current_state != TicketState.EXECUTING:
        await ticket_service.transition_ticket(
            ticket_id=ticket_id,
            to_state=TicketState.EXECUTING,
            actor_type=ActorType.HUMAN,
            reason="Execution requested",
            auto_verify=False,
            skip_cleanup=False,
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
    return await execute_ticket(ticket_id, db=db)


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


@router.get(
    "/{ticket_id}/worktree/tree",
    summary="Get file tree for a ticket's worktree",
)
async def get_worktree_tree(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the directory structure of a ticket's worktree.

    Used by the frontend FileTree component to browse files
    in the ticket's isolated workspace.
    """
    from pathlib import Path

    from app.models.board import Board
    from app.models.workspace import Workspace
    from app.services.worktree_file_service import build_file_tree

    # Verify ticket exists
    service = TicketService(db)
    ticket = await service.get_ticket_by_id(ticket_id)

    # Find the workspace for this ticket
    result = await db.execute(select(Workspace).where(Workspace.ticket_id == ticket_id))
    workspace = result.scalar_one_or_none()

    if not workspace or not workspace.worktree_path:
        raise HTTPException(
            status_code=404,
            detail="No worktree found for this ticket",
        )

    worktree_path = Path(workspace.worktree_path)

    # If the worktree path is relative, resolve it against the board's repo root
    if not worktree_path.is_absolute():
        repo_root = None
        if ticket.board_id:
            board_result = await db.execute(
                select(Board).where(Board.id == ticket.board_id)
            )
            board = board_result.scalar_one_or_none()
            if board and board.repo_root:
                repo_root = Path(board.repo_root)

        if repo_root is None:
            git_repo_path = os.environ.get("GIT_REPO_PATH")
            repo_root = Path(git_repo_path) if git_repo_path else Path.cwd()

        worktree_path = repo_root / worktree_path

    if not worktree_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Worktree directory does not exist on disk",
        )

    tree = build_file_tree(str(worktree_path))
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail="Could not build file tree",
        )

    return tree


@router.get(
    "/{ticket_id}/dependents",
    response_model=list[TicketResponse],
    summary="Get tickets blocked by this ticket",
)
async def get_ticket_dependents(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[TicketResponse]:
    """
    Get all tickets that are blocked by this ticket (downstream dependencies).

    Returns tickets where blocked_by_ticket_id = ticket_id, ordered by priority descending.
    """
    # First verify the ticket exists
    service = TicketService(db)
    await service.get_ticket_by_id(ticket_id)

    # Get all tickets blocked by this ticket
    result = await db.execute(
        select(Ticket)
        .where(Ticket.blocked_by_ticket_id == ticket_id)
        .order_by(Ticket.priority.desc().nullslast(), Ticket.created_at)
    )
    dependent_tickets = list(result.scalars().all())

    return [TicketResponse.model_validate(t) for t in dependent_tickets]


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
    from fastapi.responses import JSONResponse

    from app.schemas.planner import MAX_P0_PER_REQUEST, PriorityBucket
    from app.services.board_service import BoardService

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
                    "detail": "P0 assignments require allow_p0=true flag.",
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
        old_bucket = (
            priority_to_bucket(old_priority) if old_priority else PriorityBucket.P2
        )

        # Update priority
        new_priority = bucket_to_priority(update.priority_bucket)
        ticket.priority = new_priority

        changes_log.append(
            {
                "ticket_id": ticket.id,
                "ticket_title": ticket.title,
                "old_bucket": old_bucket.value,
                "new_bucket": update.priority_bucket.value,
                "old_priority": old_priority,
                "new_priority": new_priority,
            }
        )

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
        up_count = sum(
            1 for c in changes_log if c["new_priority"] > (c["old_priority"] or 0)
        )
        down_count = sum(
            1 for c in changes_log if c["new_priority"] < (c["old_priority"] or 0)
        )
        to_p0_count = sum(
            1
            for c in changes_log
            if c["new_bucket"] == "P0" and c["old_bucket"] != "P0"
        )

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
            payload_json=json.dumps(
                {
                    "goal_id": request.goal_id,
                    "total_updated": updated_count,
                    "up_count": up_count,
                    "down_count": down_count,
                    "to_p0_count": to_p0_count,
                    "allow_p0": request.allow_p0,
                    "changes": changes_log,
                }
            ),
        )
        db.add(event)

    await db.commit()

    return BulkPriorityUpdateResponse(
        updated=results,
        updated_count=updated_count,
        failed_count=failed_count,
    )


# ==================== Queued Message Endpoints ====================
# Like vibe-kanban, allows queuing the next prompt while execution is in progress


from pydantic import BaseModel, Field

from app.services.queued_message_service import queued_message_service


class QueueMessageRequest(BaseModel):
    """Request to queue a follow-up message."""

    message: str = Field(..., description="The follow-up prompt to execute next")


class QueueStatusResponse(BaseModel):
    """Response showing queue status for a ticket."""

    status: str = Field(..., description="Queue status: 'empty' or 'queued'")
    message: str | None = Field(None, description="The queued message (if any)")
    queued_at: str | None = Field(None, description="When the message was queued")


@router.post(
    "/{ticket_id}/queue",
    response_model=QueueStatusResponse,
    summary="Queue a follow-up message for a ticket",
)
async def queue_message(
    ticket_id: str,
    data: QueueMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> QueueStatusResponse:
    """Queue a follow-up message to be executed after the current job finishes.

    This enables a faster iteration loop for individual developers:
    - While the agent is working on one task, you can type the next instruction
    - When the current execution completes, the queued message auto-executes
    - Only one message can be queued at a time (new message replaces old)

    Similar to vibe-kanban's queued message feature.
    """
    # Verify ticket exists
    service = TicketService(db)
    await service.get_ticket_by_id(ticket_id)

    queued = queued_message_service.queue_message(ticket_id, data.message)

    return QueueStatusResponse(
        status="queued",
        message=queued.message,
        queued_at=queued.queued_at.isoformat(),
    )


@router.get(
    "/{ticket_id}/queue",
    response_model=QueueStatusResponse,
    summary="Get queue status for a ticket",
)
async def get_queue_status(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> QueueStatusResponse:
    """Get the current queue status for a ticket.

    Returns the queued message if one exists, or empty status.
    """
    # Verify ticket exists
    service = TicketService(db)
    await service.get_ticket_by_id(ticket_id)

    queued = queued_message_service.get_queued(ticket_id)

    if queued:
        return QueueStatusResponse(
            status="queued",
            message=queued.message,
            queued_at=queued.queued_at.isoformat(),
        )

    return QueueStatusResponse(status="empty", message=None, queued_at=None)


@router.delete(
    "/{ticket_id}/queue",
    response_model=QueueStatusResponse,
    summary="Cancel a queued message for a ticket",
)
async def cancel_queued_message(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> QueueStatusResponse:
    """Cancel/remove a queued message for a ticket.

    Returns empty status after cancellation.
    """
    # Verify ticket exists
    service = TicketService(db)
    await service.get_ticket_by_id(ticket_id)

    queued_message_service.cancel_queued(ticket_id)

    return QueueStatusResponse(status="empty", message=None, queued_at=None)


# ==================== Agent Activity Logs ====================
# Aggregated view of all agent execution logs for a ticket


import re
import uuid as uuid_module
from pathlib import Path

from app.models.evidence import EvidenceKind
from app.models.job import Job
from app.models.normalized_log import NormalizedLogEntry


class AgentLogEntry(BaseModel):
    """A single normalized log entry from agent execution."""

    id: str
    job_id: str
    sequence: int
    timestamp: str
    entry_type: str
    content: str
    metadata: dict = Field(default_factory=dict)
    collapsed: bool = False
    highlight: bool = False


class JobExecutionSummary(BaseModel):
    """Summary of a job's execution for display."""

    job_id: str
    job_kind: str
    job_status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    entry_count: int = 0
    entries: list[AgentLogEntry] = Field(default_factory=list)


class TicketAgentLogsResponse(BaseModel):
    """Response containing all agent execution logs for a ticket."""

    ticket_id: str
    ticket_title: str
    total_entries: int
    total_jobs: int
    executions: list[JobExecutionSummary] = Field(default_factory=list)


def parse_agent_output(
    content: str, job_id: str, timestamp: str
) -> list[AgentLogEntry]:
    """
    Parse agent stdout content into structured log entries.

    Supports two formats:
    1. cursor-agent JSON streaming (lines starting with {"type":...)
    2. Claude-style output with <thinking> blocks

    Extracts:
    - Thinking blocks
    - Assistant messages
    - Tool calls
    - System messages
    """
    entries: list[AgentLogEntry] = []
    seq = 0

    if not content or not content.strip():
        return entries

    # Check if this is cursor-agent JSON streaming format
    lines = content.strip().split("\n")
    first_line = lines[0].strip() if lines else ""

    if first_line.startswith('{"type":'):
        # Parse cursor-agent JSON streaming format
        return parse_cursor_json_output(content, job_id, timestamp)

    # Fall back to Claude-style parsing
    # Check for thinking blocks (Claude style)
    thinking_pattern = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)
    thinking_matches = thinking_pattern.findall(content)

    for thinking in thinking_matches:
        if thinking.strip():
            entries.append(
                AgentLogEntry(
                    id=str(uuid_module.uuid4()),
                    job_id=job_id,
                    sequence=seq,
                    timestamp=timestamp,
                    entry_type="thinking",
                    content=thinking.strip(),
                    metadata={"collapsed": True},
                    collapsed=True,
                    highlight=False,
                )
            )
            seq += 1

    # Remove thinking blocks from content for further parsing
    content_without_thinking = thinking_pattern.sub("", content)

    # Check for todo lists (look for patterns like "- [ ]" or numbered items with checkmarks)
    todo_pattern = re.compile(
        r"(?:^|\n)(?:[-*]\s*\[[ xX✓✗]\].*?(?:\n|$))+", re.MULTILINE
    )
    todo_match = todo_pattern.search(content_without_thinking)

    if todo_match:
        todos_text = todo_match.group(0).strip()
        entries.append(
            AgentLogEntry(
                id=str(uuid_module.uuid4()),
                job_id=job_id,
                sequence=seq,
                timestamp=timestamp,
                entry_type="todo_list",
                content=todos_text,
                metadata={"todos": parse_todos_from_text(todos_text)},
                collapsed=False,
                highlight=False,
            )
        )
        seq += 1

    # The main content is the assistant's response
    # Clean up the content and treat it as the main message
    main_content = content_without_thinking.strip()

    if main_content:
        entries.append(
            AgentLogEntry(
                id=str(uuid_module.uuid4()),
                job_id=job_id,
                sequence=seq,
                timestamp=timestamp,
                entry_type="assistant_message",
                content=main_content,
                metadata={},
                collapsed=False,
                highlight=False,
            )
        )
        seq += 1

    return entries


def parse_cursor_json_output(
    content: str, job_id: str, timestamp: str
) -> list[AgentLogEntry]:
    """
    Parse cursor-agent JSON streaming output into structured log entries.

    Handles JSON lines with types: system, user, assistant, thinking, tool_call, result
    """
    import json

    entries: list[AgentLogEntry] = []
    seq = 0

    # Coalescing state for streaming messages
    current_thinking = ""
    current_assistant = ""

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON line - skip or treat as system message
            if line and not line.startswith("{"):
                entries.append(
                    AgentLogEntry(
                        id=str(uuid_module.uuid4()),
                        job_id=job_id,
                        sequence=seq,
                        timestamp=timestamp,
                        entry_type="system_message",
                        content=line,
                        metadata={},
                        collapsed=False,
                        highlight=False,
                    )
                )
                seq += 1
            continue

        msg_type = data.get("type", "")

        if msg_type == "system":
            model = data.get("model")
            if model:
                entries.append(
                    AgentLogEntry(
                        id=str(uuid_module.uuid4()),
                        job_id=job_id,
                        sequence=seq,
                        timestamp=timestamp,
                        entry_type="system_message",
                        content=f"🤖 Model: {model}",
                        metadata={"model": model},
                        collapsed=False,
                        highlight=False,
                    )
                )
                seq += 1

        elif msg_type == "thinking":
            subtype = data.get("subtype", "")
            if subtype == "delta":
                text = data.get("text", "")
                current_thinking += text
            elif subtype == "completed":
                if current_thinking:
                    entries.append(
                        AgentLogEntry(
                            id=str(uuid_module.uuid4()),
                            job_id=job_id,
                            sequence=seq,
                            timestamp=timestamp,
                            entry_type="thinking",
                            content=current_thinking,
                            metadata={"collapsed": True},
                            collapsed=True,
                            highlight=False,
                        )
                    )
                    seq += 1
                    current_thinking = ""

        elif msg_type == "assistant":
            message = data.get("message", {})
            content_parts = message.get("content", [])
            text = ""
            for part in content_parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += part.get("text", "")
                elif isinstance(part, str):
                    text += part

            if text:
                current_assistant += text

        elif msg_type == "tool_call":
            subtype = data.get("subtype", "")
            tool_call = data.get("tool_call", {})

            # Parse tool type and content
            tool_name, content_text = _parse_cursor_tool_call(tool_call)

            if subtype == "started":
                entries.append(
                    AgentLogEntry(
                        id=str(uuid_module.uuid4()),
                        job_id=job_id,
                        sequence=seq,
                        timestamp=timestamp,
                        entry_type="tool_call",
                        content=content_text,
                        metadata={"tool_name": tool_name, "status": "started"},
                        collapsed=False,
                        highlight=False,
                    )
                )
                seq += 1
            elif subtype == "completed":
                result_text = _extract_cursor_tool_result(tool_call)
                entries.append(
                    AgentLogEntry(
                        id=str(uuid_module.uuid4()),
                        job_id=job_id,
                        sequence=seq,
                        timestamp=timestamp,
                        entry_type="tool_call",
                        content=f"{content_text}\n→ {result_text}"
                        if result_text
                        else content_text,
                        metadata={"tool_name": tool_name, "status": "completed"},
                        collapsed=False,
                        highlight=False,
                    )
                )
                seq += 1

    # Flush any remaining assistant content
    if current_assistant:
        entries.append(
            AgentLogEntry(
                id=str(uuid_module.uuid4()),
                job_id=job_id,
                sequence=seq,
                timestamp=timestamp,
                entry_type="assistant_message",
                content=current_assistant,
                metadata={},
                collapsed=False,
                highlight=False,
            )
        )
        seq += 1

    # Flush any remaining thinking content
    if current_thinking:
        entries.append(
            AgentLogEntry(
                id=str(uuid_module.uuid4()),
                job_id=job_id,
                sequence=seq,
                timestamp=timestamp,
                entry_type="thinking",
                content=current_thinking,
                metadata={"collapsed": True},
                collapsed=True,
                highlight=False,
            )
        )
        seq += 1

    return entries


def _parse_cursor_tool_call(tool_call: dict) -> tuple[str, str]:
    """Parse cursor-agent tool call to extract name and display content."""
    if "readToolCall" in tool_call:
        args = tool_call["readToolCall"].get("args", {})
        path = args.get("path", "unknown")
        # Strip common worktree prefixes for cleaner display
        if "/.smartkanban/worktrees/" in path:
            path = path.split("/.smartkanban/worktrees/")[1]
            if "/" in path:
                path = path.split("/", 1)[1]  # Remove UUID prefix
        return "read_file", f"📖 Read: {path}"

    if "editToolCall" in tool_call:
        args = tool_call["editToolCall"].get("args", {})
        path = args.get("path", "unknown")
        if "/.smartkanban/worktrees/" in path:
            path = path.split("/.smartkanban/worktrees/")[1]
            if "/" in path:
                path = path.split("/", 1)[1]
        return "edit_file", f"✏️ Edit: {path}"

    if "lsToolCall" in tool_call:
        args = tool_call["lsToolCall"].get("args", {})
        path = args.get("path", ".")
        return "list_dir", f"📁 List: {path}"

    if "globToolCall" in tool_call:
        args = tool_call["globToolCall"].get("args", {})
        pattern = args.get("globPattern", "*")
        return "glob", f"🔍 Glob: {pattern}"

    if "grepToolCall" in tool_call:
        args = tool_call["grepToolCall"].get("args", {})
        pattern = args.get("pattern", "")
        return "grep", f"🔍 Grep: {pattern}"

    if "shellToolCall" in tool_call:
        args = tool_call["shellToolCall"].get("args", {})
        command = args.get("command", "")
        return "shell", f"💻 Shell: {command}"

    return "unknown", "🔧 Tool call"


def _extract_cursor_tool_result(tool_call: dict) -> str:
    """Extract a summary of cursor-agent tool result."""
    for key in [
        "readToolCall",
        "editToolCall",
        "lsToolCall",
        "globToolCall",
        "grepToolCall",
        "shellToolCall",
    ]:
        if key in tool_call:
            result = tool_call[key].get("result", {})
            if "success" in result:
                success = result["success"]
                if key == "editToolCall":
                    lines_added = success.get("linesAdded", 0)
                    lines_removed = success.get("linesRemoved", 0)
                    return f"+{lines_added} -{lines_removed} lines"
                elif key == "shellToolCall":
                    exit_code = success.get("exitCode", 0)
                    return f"exit code: {exit_code}"
                elif key == "globToolCall":
                    total = success.get("totalFiles", 0)
                    return f"{total} files"
                elif key == "readToolCall":
                    total_lines = success.get("totalLines", 0)
                    return f"{total_lines} lines" if total_lines else "read"
            elif "error" in result:
                return f"❌ {str(result['error'])[:50]}"
    return ""


def parse_todos_from_text(text: str) -> list[dict]:
    """Parse todo items from text into structured format."""
    todos = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match "- [ ] task" or "- [x] task" patterns
        match = re.match(r"^[-*]\s*\[([xX✓ ])\]\s*(.+)$", line)
        if match:
            checked = match.group(1).lower() in ("x", "✓")
            content = match.group(2).strip()
            todos.append(
                {
                    "content": content,
                    "completed": checked,
                }
            )

    return todos


@router.get(
    "/{ticket_id}/agent-logs",
    response_model=TicketAgentLogsResponse,
    summary="Get all agent execution logs for a ticket",
)
async def get_ticket_agent_logs(
    ticket_id: str,
    include_entries: bool = True,
    db: AsyncSession = Depends(get_db),
) -> TicketAgentLogsResponse:
    """
    Get all agent execution logs for a ticket across all jobs.

    This provides a complete view of the agent's chain of thought, tool calls,
    file edits, and other actions taken during ticket execution.

    Like vibe-kanban's execution_process_logs, this allows users to:
    - Review the agent's reasoning process
    - See what tools were used and why
    - Debug issues with ticket execution
    - Understand how the agent approached the task

    Reads from Evidence stdout files (actual agent output) rather than
    orchestrator logs.

    Args:
        ticket_id: The ticket ID
        include_entries: If True (default), include full log entries.
                        If False, only return summary info.

    Returns:
        All agent conversation/output grouped by job execution.
    """
    import os

    from sqlalchemy.orm import selectinload

    from app.models.board import Board

    # Verify ticket exists and get title
    service = TicketService(db)
    ticket = await service.get_ticket_by_id(ticket_id)

    # Get repo root from the ticket's board (authoritative source)
    repo_root = None
    if ticket.board_id:
        board_result = await db.execute(
            select(Board).where(Board.id == ticket.board_id)
        )
        board = board_result.scalar_one_or_none()
        if board and board.repo_root:
            repo_root = Path(board.repo_root)

    # Fallback to environment or cwd
    if repo_root is None or not repo_root.exists():
        git_repo_path = os.environ.get("GIT_REPO_PATH")
        if git_repo_path:
            repo_root = Path(git_repo_path)
        else:
            repo_root = Path.cwd()

    # Get all jobs for this ticket with their evidence
    result = await db.execute(
        select(Job)
        .where(Job.ticket_id == ticket_id)
        .options(selectinload(Job.evidence))
        .order_by(Job.created_at.desc())
    )
    jobs = list(result.scalars().all())

    executions: list[JobExecutionSummary] = []
    total_entries = 0

    for job in jobs:
        # Calculate duration if job is finished
        duration = None
        if job.started_at and job.finished_at:
            duration = (job.finished_at - job.started_at).total_seconds()

        timestamp = (
            job.started_at.isoformat() if job.started_at else job.created_at.isoformat()
        )

        # Build entries from Evidence stdout files
        entries: list[AgentLogEntry] = []

        if include_entries:
            # Get executor evidence (the actual agent output)
            executor_evidence = [
                ev
                for ev in job.evidence
                if ev.kind == EvidenceKind.EXECUTOR_STDOUT.value
            ]

            for ev in executor_evidence:
                if ev.stdout_path:
                    try:
                        # Resolve the stdout path - try multiple locations
                        stdout_path = repo_root / ev.stdout_path

                        # If not found at repo root, try relative to cwd
                        if not stdout_path.exists():
                            stdout_path = Path.cwd() / ev.stdout_path

                        # If still not found, try absolute path
                        if not stdout_path.exists() and ev.stdout_path.startswith("/"):
                            stdout_path = Path(ev.stdout_path)

                        if stdout_path.exists():
                            content = stdout_path.read_text()
                            if content.strip():
                                # Parse the agent output into structured entries
                                parsed = parse_agent_output(content, job.id, timestamp)
                                entries.extend(parsed)
                        else:
                            # File not found - add info entry
                            entries.append(
                                AgentLogEntry(
                                    id=str(uuid_module.uuid4()),
                                    job_id=job.id,
                                    sequence=0,
                                    timestamp=timestamp,
                                    entry_type="system_message",
                                    content=f"Agent output file not found: {ev.stdout_path}",
                                    metadata={"repo_root": str(repo_root)},
                                    collapsed=False,
                                    highlight=False,
                                )
                            )
                    except Exception as e:
                        # If we can't read the file, add an error entry
                        entries.append(
                            AgentLogEntry(
                                id=str(uuid_module.uuid4()),
                                job_id=job.id,
                                sequence=0,
                                timestamp=timestamp,
                                entry_type="error",
                                content=f"Could not read agent output: {str(e)}",
                                metadata={},
                                collapsed=False,
                                highlight=True,
                            )
                        )

            # If no executor evidence, try to get from normalized logs as fallback
            if not entries:
                # Fallback to normalized_logs table
                logs_result = await db.execute(
                    select(NormalizedLogEntry)
                    .where(NormalizedLogEntry.job_id == job.id)
                    .order_by(NormalizedLogEntry.sequence)
                )
                logs = list(logs_result.scalars().all())

                for log in logs:
                    entries.append(
                        AgentLogEntry(
                            id=log.id,
                            job_id=log.job_id,
                            sequence=log.sequence,
                            timestamp=log.timestamp.isoformat()
                            if log.timestamp
                            else "",
                            entry_type=log.entry_type.value if log.entry_type else "",
                            content=log.content,
                            metadata=log.entry_metadata or {},
                            collapsed=log.collapsed or False,
                            highlight=log.highlight or False,
                        )
                    )

        total_entries += len(entries)

        executions.append(
            JobExecutionSummary(
                job_id=job.id,
                job_kind=job.kind,
                job_status=job.status,
                started_at=job.started_at.isoformat() if job.started_at else None,
                finished_at=job.finished_at.isoformat() if job.finished_at else None,
                duration_seconds=duration,
                entry_count=len(entries),
                entries=entries,
            )
        )

    return TicketAgentLogsResponse(
        ticket_id=ticket_id,
        ticket_title=ticket.title,
        total_entries=total_entries,
        total_jobs=len(jobs),
        executions=executions,
    )
