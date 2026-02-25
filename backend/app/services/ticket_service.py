"""Service layer for Ticket operations with state machine enforcement."""

import asyncio
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database_sync import get_sync_db
from app.exceptions import InvalidStateTransitionError, ResourceNotFoundError
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.schemas.ticket import TicketCreate, TicketResponse, TicketsByState
from app.services.workspace_service import WorkspaceService
from app.state_machine import (
    ActorType,
    EventType,
    TicketState,
    is_terminal_state,
    validate_transition,
)

logger = logging.getLogger(__name__)

# Thread pool for running blocking workspace cleanup operations
_cleanup_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="workspace_cleanup")


class TicketService:
    """Service class for Ticket business logic with state machine enforcement."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_ticket(self, data: TicketCreate) -> Ticket:
        """
        Create a new ticket in the 'proposed' state.
        Also creates an initial TicketEvent for the creation.

        Args:
            data: Ticket creation data

        Returns:
            The created Ticket instance
        """
        # Validate blocked_by_ticket_id if provided
        blocked_by_title = None
        if data.blocked_by_ticket_id:
            result = await self.db.execute(
                select(Ticket).where(Ticket.id == data.blocked_by_ticket_id)
            )
            blocker = result.scalar_one_or_none()
            if not blocker:
                raise ResourceNotFoundError("Blocking Ticket", data.blocked_by_ticket_id)
            blocked_by_title = blocker.title

        # Fetch board_id from the parent goal
        from app.models.goal import Goal

        goal = await self.db.get(Goal, data.goal_id)
        if not goal:
            raise ResourceNotFoundError("Goal", data.goal_id)

        # Create the ticket
        ticket = Ticket(
            goal_id=data.goal_id,
            board_id=goal.board_id,
            title=data.title,
            description=data.description,
            state=TicketState.PROPOSED.value,
            priority=data.priority,
            blocked_by_ticket_id=data.blocked_by_ticket_id,
        )
        self.db.add(ticket)
        await self.db.flush()

        # Create the initial event
        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.CREATED.value,
            from_state=None,
            to_state=TicketState.PROPOSED.value,
            actor_type=data.actor_type.value,
            actor_id=data.actor_id,
            reason="Ticket created",
            payload_json=json.dumps(
                {
                    "title": data.title,
                    "description": data.description,
                    "goal_id": data.goal_id,
                    "priority": data.priority,
                    "blocked_by_ticket_id": data.blocked_by_ticket_id,
                    "blocked_by_title": blocked_by_title,
                }
            ),
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(ticket)

        return ticket

    async def get_ticket_by_id(self, ticket_id: str) -> Ticket:
        """
        Get a ticket by its ID.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            The Ticket instance

        Raises:
            ResourceNotFoundError: If the ticket is not found
        """
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.goal),
                selectinload(Ticket.blocked_by),  # Load blocker relationship
            )
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)
        return ticket

    async def transition_ticket(
        self,
        ticket_id: str,
        to_state: TicketState,
        actor_type: ActorType,
        actor_id: str | None = None,
        reason: str | None = None,
        auto_verify: bool = True,
        skip_cleanup: bool = False,
    ) -> Ticket:
        """
        Transition a ticket to a new state.
        Validates the transition and creates a TicketEvent atomically.

        Args:
            ticket_id: The UUID of the ticket
            to_state: The target state
            actor_type: The type of actor performing the transition
            actor_id: Optional ID of the actor
            reason: Optional reason for the transition
            auto_verify: If True, auto-enqueue verify job when entering verifying state
            skip_cleanup: If True, skip workspace cleanup for terminal states
                (use when caller handles cleanup separately to avoid SQLite deadlocks)

        Returns:
            The updated Ticket instance

        Raises:
            ResourceNotFoundError: If the ticket is not found
            InvalidStateTransitionError: If the transition is not valid
        """
        ticket = await self.get_ticket_by_id(ticket_id)
        from_state = TicketState(ticket.state)

        # Validate the transition
        if not validate_transition(from_state, to_state):
            raise InvalidStateTransitionError(from_state.value, to_state.value)

        # Update the ticket state
        ticket.state = to_state.value

        # Create the transition event
        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.TRANSITIONED.value,
            from_state=from_state.value,
            to_state=to_state.value,
            actor_type=actor_type.value,
            actor_id=actor_id,
            reason=reason,
            payload_json=None,
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(ticket)

        # Trigger workspace cleanup for terminal states
        if is_terminal_state(to_state) and not skip_cleanup:
            await self._cleanup_workspace_async(ticket_id)

        # Auto-trigger verification when entering verifying state
        if auto_verify and to_state == TicketState.VERIFYING:
            await self._enqueue_verify_job_async(ticket_id)

        return ticket

    async def _enqueue_verify_job_async(self, ticket_id: str) -> str | None:
        """
        Asynchronously enqueue a verify job for a ticket (idempotent).

        Idempotency: Only creates a new verify job if there is no active
        (queued or running) verify job for this ticket. This prevents
        duplicate verify jobs from race conditions or retries.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            The job ID if created, None if skipped (already active).
        """
        from app.models.job import Job, JobKind, JobStatus

        try:
            # IDEMPOTENCY CHECK: Is there already an active verify job?
            active_verify_result = await self.db.execute(
                select(Job).where(
                    Job.ticket_id == ticket_id,
                    Job.kind == JobKind.VERIFY.value,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            )
            active_verify = active_verify_result.scalar_one_or_none()

            if active_verify:
                logger.info(f"Skipping verify enqueue for ticket {ticket_id} - already has active job {active_verify.id}")
                return None

            # Create the job record
            job = Job(
                ticket_id=ticket_id,
                kind=JobKind.VERIFY.value,
                status=JobStatus.QUEUED.value,
            )
            self.db.add(job)
            await self.db.flush()
            await self.db.refresh(job)

            # CRITICAL: Commit BEFORE dispatching to avoid SQLite deadlock.
            # The SQLite in-process worker picks up tasks immediately and tries
            # to write to the same DB. If we hold the write lock (uncommitted
            # flush), the worker blocks → deadlock with the event loop.
            await self.db.commit()

            # Enqueue the verify task via unified dispatch
            from app.services.task_dispatch import enqueue_task
            task = enqueue_task("verify_ticket", args=[job.id])

            # Store the task ID (new transaction after commit)
            job.celery_task_id = task.id
            await self.db.flush()

            logger.info(f"Auto-enqueued verify job {job.id} for ticket {ticket_id}")
            return job.id

        except Exception as e:
            logger.error(f"Failed to auto-enqueue verify job for ticket {ticket_id}: {e}")
            return None

    async def _cleanup_workspace_async(self, ticket_id: str) -> None:
        """
        Clean up the workspace for a ticket asynchronously.

        Runs the blocking git operations in a thread pool executor.

        Args:
            ticket_id: The UUID of the ticket
        """
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                _cleanup_executor,
                self._cleanup_workspace_sync,
                ticket_id,
            )
        except Exception as e:
            # Log but don't fail the transition if cleanup fails
            logger.warning(f"Failed to cleanup workspace for ticket {ticket_id}: {e}")

    @staticmethod
    def _cleanup_workspace_sync(ticket_id: str) -> bool:
        """
        Synchronously clean up the workspace for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            True if cleanup was performed, False otherwise
        """
        try:
            with get_sync_db() as db:
                workspace_service = WorkspaceService(db)
                return workspace_service.cleanup_worktree(ticket_id)
        except Exception as e:
            logger.warning(f"Workspace cleanup error for ticket {ticket_id}: {e}")
            return False

    async def get_board(self, board_id: str | None = None) -> list[TicketsByState]:
        """
        Get tickets grouped by state for the board view.
        Tickets are ordered by priority (descending, nulls last) within each state.

        Args:
            board_id: Optional board ID to filter tickets. If None, returns all tickets.

        Returns:
            List of TicketsByState objects
        """
        query = (
            select(Ticket)
            .options(selectinload(Ticket.goal))  # Eagerly load goal to avoid N+1
            .options(selectinload(Ticket.blocked_by))  # Eagerly load blocker ticket
            .order_by(
                Ticket.priority.desc().nulls_last(),
                Ticket.created_at.desc(),
            )
        )

        # Filter by board_id if provided
        if board_id is not None:
            query = query.where(Ticket.board_id == board_id)

        result = await self.db.execute(query)
        tickets = result.scalars().all()

        # Group tickets by state
        tickets_by_state: dict[str, list[Ticket]] = defaultdict(list)
        for ticket in tickets:
            tickets_by_state[ticket.state].append(ticket)

        # Build response with all states (even empty ones)
        columns = []
        for state in TicketState:
            # Convert tickets to response format and add blocker titles
            ticket_list = tickets_by_state.get(state.value, [])
            ticket_responses = []
            for ticket in ticket_list:
                ticket_dict = TicketResponse.model_validate(ticket).model_dump()
                # Add blocker title if ticket is blocked
                if ticket.blocked_by_ticket_id and ticket.blocked_by:
                    ticket_dict["blocked_by_ticket_title"] = ticket.blocked_by.title
                ticket_responses.append(ticket_dict)

            columns.append(
                TicketsByState(
                    state=state,
                    tickets=ticket_responses,
                )
            )

        return columns

    async def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        """
        Get all events for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            List of TicketEvent instances ordered by created_at

        Raises:
            ResourceNotFoundError: If the ticket is not found
        """
        # First verify the ticket exists
        await self.get_ticket_by_id(ticket_id)

        result = await self.db.execute(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_all_tickets(self, board_id: str | None = None) -> int:
        """
        Delete all tickets from the database.

        This will cascade delete all associated:
        - Jobs
        - Revisions (and their review comments/summaries)
        - Ticket events
        - Workspaces
        - Evidence

        Args:
            board_id: Optional board ID to limit deletion to specific board

        Returns:
            Number of tickets deleted
        """
        from sqlalchemy import delete
        from app.models.workspace import Workspace

        # Build query
        query = select(Ticket)
        if board_id:
            query = query.where(Ticket.board_id == board_id)

        # Get all ticket IDs for workspace cleanup
        result = await self.db.execute(query)
        tickets = result.scalars().all()
        ticket_ids = [t.id for t in tickets]
        count = len(ticket_ids)

        if count == 0:
            return 0

        # Clean up workspaces asynchronously (best effort)
        cleanup_tasks = []
        for ticket_id in ticket_ids:
            task = asyncio.create_task(self._cleanup_workspace_async(ticket_id))
            cleanup_tasks.append(task)

        # Wait for cleanup with timeout (don't block deletion if cleanup fails)
        if cleanup_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*cleanup_tasks, return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning("Workspace cleanup timed out during bulk ticket deletion")

        # Delete all tickets (cascade will handle related records)
        delete_query = delete(Ticket)
        if board_id:
            delete_query = delete_query.where(Ticket.board_id == board_id)

        await self.db.execute(delete_query)
        await self.db.commit()

        logger.info(f"Deleted {count} tickets" + (f" from board {board_id}" if board_id else ""))
        return count
