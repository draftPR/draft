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
from app.schemas.ticket import TicketCreate, TicketsByState
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
        # Create the ticket
        ticket = Ticket(
            goal_id=data.goal_id,
            title=data.title,
            description=data.description,
            state=TicketState.PROPOSED.value,
            priority=data.priority,
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
            .options(selectinload(Ticket.goal))
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
        if is_terminal_state(to_state):
            await self._cleanup_workspace_async(ticket_id)

        # Auto-trigger verification when entering verifying state
        if auto_verify and to_state == TicketState.VERIFYING:
            await self._enqueue_verify_job_async(ticket_id)

        return ticket

    async def _enqueue_verify_job_async(self, ticket_id: str) -> str | None:
        """
        Asynchronously enqueue a verify job for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            The job ID if successful, None otherwise.
        """
        from app.models.job import Job, JobKind, JobStatus

        try:
            # Import here to avoid circular dependency
            from app.worker import verify_ticket_task

            # Create the job record
            job = Job(
                ticket_id=ticket_id,
                kind=JobKind.VERIFY.value,
                status=JobStatus.QUEUED.value,
            )
            self.db.add(job)
            await self.db.flush()
            await self.db.refresh(job)

            # Enqueue the Celery task
            task = verify_ticket_task.delay(job.id)

            # Store the Celery task ID
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

    async def get_board(self) -> list[TicketsByState]:
        """
        Get all tickets grouped by state for the board view.
        Tickets are ordered by priority (descending, nulls last) within each state.

        Returns:
            List of TicketsByState objects
        """
        result = await self.db.execute(
            select(Ticket).order_by(
                Ticket.priority.desc().nulls_last(),
                Ticket.created_at.desc(),
            )
        )
        tickets = result.scalars().all()

        # Group tickets by state
        tickets_by_state: dict[str, list[Ticket]] = defaultdict(list)
        for ticket in tickets:
            tickets_by_state[ticket.state].append(ticket)

        # Build response with all states (even empty ones)
        columns = []
        for state in TicketState:
            columns.append(
                TicketsByState(
                    state=state,
                    tickets=tickets_by_state.get(state.value, []),
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
