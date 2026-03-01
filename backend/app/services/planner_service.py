"""Planner service for automated workflow decisions.

The planner runs in "tick" mode - each tick evaluates the board state
and takes actions to move work forward:

1. Pick next ticket (deterministic):
   - If no EXECUTING or VERIFYING ticket exists, pick highest priority PLANNED ticket
   - Enqueue execute job for the selected ticket

2. Handle blocked tickets (LLM-powered):
   - For BLOCKED tickets without follow-ups, generate follow-up proposals
   - Auto-create follow-up tickets in PROPOSED state
   - Respects caps: max_followups_per_ticket and max_followups_per_tick
   - Skips certain blocker reasons (e.g., "no changes produced")

3. Generate reflections (LLM-powered):
   - For DONE tickets without reflections, generate summary comments
   - Create TicketEvent with the reflection (never modifies ticket text)

PERMISSIONS (what the planner CAN and CANNOT do):
  CAN:
    - Create tickets in PROPOSED state only (follow-ups)
    - Enqueue EXECUTE jobs for PLANNED tickets
    - Add COMMENT events (reflections, action logs)
  CANNOT:
    - Transition tickets between states
    - Delete anything
    - Modify ticket title/description
    - Create tickets in any state other than PROPOSED

CONCURRENCY SAFETY:
  - Uses a lock row in planner_locks table
  - Only one tick can run at a time
  - Celery jobs are enqueued AFTER DB commit

NOTE: For ticket generation from goals, use TicketGenerationService instead.
This service focuses on the tick-based autopilot workflow.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job, JobKind, JobStatus
from app.models.planner_lock import PlannerLock
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent

# Deferred import to avoid circular dependency with async database
# from app.services.orchestrator_log import add_orchestrator_log  # imported inside methods
from app.schemas.planner import PlannerAction, PlannerActionType, PlannerTickResponse
from app.services.config_service import ConfigService, PlannerConfig
from app.services.llm_service import LLMService
from app.state_machine import ActorType, EventType, TicketState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Event type for planner reflections (using COMMENT)
REFLECTION_EVENT_TYPE = EventType.COMMENT.value
REFLECTION_MARKER = "planner_reflection"

# Payload marker for follow-up link
FOLLOWUP_MARKER = "planner_followup_created"

# Lock settings
PLANNER_LOCK_KEY = "planner_tick"
LOCK_STALE_MINUTES = 10  # Consider lock stale after this many minutes


class PlannerLockError(Exception):
    """Raised when planner lock cannot be acquired."""

    pass


@dataclass
class FollowUpProposal:
    """Proposed follow-up ticket for a blocked ticket."""

    title: str
    description: str
    verification: list[str]


@dataclass
class ReflectionSummary:
    """Generated reflection summary for a completed ticket."""

    summary: str


class PlannerService:
    """Service for automated workflow planning decisions.

    The planner operates deterministically for ticket selection and uses
    LLM only for generating follow-up proposals and reflections.

    Thread safety:
        Uses a database lock row to ensure only one tick runs at a time.
        This prevents race conditions where two concurrent ticks might
        both see "no executing ticket" and both enqueue jobs.

    For ticket generation from goals, use TicketGenerationService instead.
    """

    def __init__(
        self,
        db: AsyncSession,
        config: PlannerConfig | None = None,
        llm_service: LLMService | None = None,
    ):
        """Initialize the planner service.

        Args:
            db: Async database session.
            config: Planner configuration. If None, loads from config file.
            llm_service: LLM service instance. If None, creates one.
        """
        self.db = db
        self._lock_owner_id = str(uuid.uuid4())  # Unique ID for this tick instance

        if config is None:
            # Use the kanban project root (parent of backend) for config
            from pathlib import Path

            kanban_root = Path(__file__).parent.parent.parent.parent
            config_service = ConfigService(repo_path=kanban_root)
            config = config_service.get_planner_config()

        self.config = config

        if llm_service is None:
            llm_service = LLMService(config)

        self.llm_service = llm_service

    async def tick(self, force_execute: bool = False) -> PlannerTickResponse:
        """Run one decision cycle of the planner.

        Evaluates the current board state and takes appropriate actions:
        1. Pick and execute next planned ticket (if no active execution)
        2. Generate follow-ups for blocked tickets (with caps)
        3. Generate reflections for done tickets

        Args:
            force_execute: If True, queue planned tickets regardless of config.
                           Used by /planner/start to explicitly trigger execution.

        Thread safety:
            Acquires a database lock before processing. If another tick
            is already running, raises PlannerLockError.

        Returns:
            PlannerTickResponse with actions taken and summary.

        Raises:
            PlannerLockError: If lock cannot be acquired (another tick is running).

        INVARIANT: Lock acquisition MUST be the first DB operation in this method.
        The lock acquire may rollback on IntegrityError, which would wipe any
        previously staged changes. Do not add DB writes before _acquire_lock().
        """
        # Local import to avoid circular dependency with async database at module load
        from app.services.orchestrator_log import add_orchestrator_log

        actions: list[PlannerAction] = []
        jobs_to_enqueue: list[str] = []  # Job IDs to enqueue AFTER commit

        # INVARIANT: This MUST be the first DB operation. See docstring.
        # Lock acquisition may rollback on IntegrityError.
        await self._acquire_lock()
        add_orchestrator_log(
            "INFO", "Planner tick started", {"owner": self._lock_owner_id}
        )

        try:
            # 1. Queue planned tickets for execution
            # force_execute bypasses config AND queues ALL planned tickets (used by /planner/start)
            # Normal auto_execute only queues one at a time
            if force_execute:
                # Queue ALL planned tickets when user explicitly starts autopilot
                add_orchestrator_log(
                    "INFO", "Force execute: queueing all planned tickets"
                )
                execute_results = await self._queue_all_planned_tickets()
                for action, job_id in execute_results:
                    actions.append(action)
                    if job_id:
                        jobs_to_enqueue.append(job_id)
                        add_orchestrator_log(
                            "INFO",
                            f"Queued ticket for execution: {action.ticket_title}",
                            {"ticket_id": action.ticket_id, "job_id": job_id},
                        )
                if not execute_results:
                    add_orchestrator_log("INFO", "No planned tickets to queue")
            elif self.config.features.auto_execute:
                # Normal periodic tick: queue one at a time
                if not await self._has_active_execution():
                    add_orchestrator_log(
                        "INFO", "No active execution, checking for planned tickets"
                    )
                    execute_results = await self._pick_and_execute_next()
                    for action, job_id in execute_results:
                        actions.append(action)
                        if job_id:
                            jobs_to_enqueue.append(job_id)
                            add_orchestrator_log(
                                "INFO",
                                f"Queued ticket for execution: {action.ticket_title}",
                                {"ticket_id": action.ticket_id, "job_id": job_id},
                            )
                    if not execute_results:
                        # No planned tickets to queue
                        logger.debug("No planned tickets to queue")
                        add_orchestrator_log("INFO", "No planned tickets to queue")
                else:
                    # Log that we skipped due to active execution
                    add_orchestrator_log(
                        "INFO",
                        "Skipped: Active execution in progress",
                        {"reason": "executing or verifying ticket exists"},
                    )
                    actions.append(
                        PlannerAction(
                            action_type=PlannerActionType.SKIPPED,
                            ticket_id="",
                            ticket_title=None,
                            details={
                                "reason": "Active execution in progress (executing or verifying ticket exists)"
                            },
                        )
                    )

            # 2. Unblock tickets whose blockers are now done
            unblock_actions = await self._unblock_ready_tickets()
            actions.extend(unblock_actions)
            if unblock_actions:
                for ua in unblock_actions:
                    add_orchestrator_log(
                        "INFO",
                        f"Unblocked ticket: '{ua.ticket_title}'",
                        {
                            "ticket_id": ua.ticket_id,
                            "blocker_ticket_id": ua.details.get("blocker_ticket_id"),
                            "blocker_title": ua.details.get("blocker_title"),
                        },
                    )

            # 3. Handle blocked tickets (LLM-powered, with caps)
            if self.config.features.propose_followups:
                followup_actions = await self._handle_blocked_tickets()
                actions.extend(followup_actions)

            # 4. Generate reflections (LLM-powered)
            if self.config.features.generate_reflections:
                reflection_actions = await self._generate_reflections()
                actions.extend(reflection_actions)

            # 5. UDAR incremental replanning (Phase 3)
            if (
                self.config.udar.enabled
                and self.config.udar.enable_incremental_replanning
            ):
                add_orchestrator_log(
                    "INFO",
                    "UDAR incremental replanning enabled, checking for completed tickets",
                )
                replan_actions = await self._udar_incremental_replan()
                actions.extend(replan_actions)
                if replan_actions:
                    add_orchestrator_log(
                        "INFO",
                        f"UDAR generated {len(replan_actions)} follow-up proposals",
                        {"count": len(replan_actions)},
                    )

            # 6. Auto-merge DONE tickets with autonomy enabled
            auto_merge_actions = await self._auto_merge_done_tickets()
            actions.extend(auto_merge_actions)
            if auto_merge_actions:
                add_orchestrator_log(
                    "INFO",
                    f"Auto-merged {len(auto_merge_actions)} ticket(s)",
                    {"count": len(auto_merge_actions)},
                )

            # Commit all DB changes BEFORE enqueueing Celery jobs
            await self.db.commit()
            add_orchestrator_log("DEBUG", "DB changes committed")

        finally:
            # Always release lock, even on error
            await self._release_lock()

        # Enqueue Celery jobs AFTER commit (prevents stale DB state)
        for job_id in jobs_to_enqueue:
            await self._enqueue_celery_job(job_id)
            add_orchestrator_log(
                "INFO", f"Celery task enqueued for job {job_id[:8]}..."
            )

        # Generate summary
        summary = self._generate_summary(actions)
        add_orchestrator_log(
            "INFO",
            f"Planner tick completed: {summary}",
            {"actions_count": len(actions), "jobs_enqueued": len(jobs_to_enqueue)},
        )

        return PlannerTickResponse(
            actions=actions,
            summary=summary,
        )

    # =========================================================================
    # LOCK MANAGEMENT
    # =========================================================================

    async def _acquire_lock(self) -> None:
        """Acquire the planner lock atomically.

        Uses UPDATE-then-INSERT pattern to prevent race conditions:
        1. Try to UPDATE an existing stale lock (atomic claim)
        2. If no rows updated, try INSERT (no lock exists)
        3. If INSERT fails with IntegrityError, lock is held by another tick

        This prevents the race where two requests both see a stale lock
        and both try to claim it.

        Raises:
            PlannerLockError: If lock cannot be acquired.
        """
        stale_threshold = datetime.now(UTC) - timedelta(minutes=LOCK_STALE_MINUTES)
        now = datetime.now(UTC)

        # STEP 1: Try to atomically claim a stale lock via UPDATE
        # This is safe because UPDATE with WHERE is atomic - only one request wins
        update_result = await self.db.execute(
            update(PlannerLock)
            .where(
                and_(
                    PlannerLock.lock_key == PLANNER_LOCK_KEY,
                    PlannerLock.acquired_at < stale_threshold,
                )
            )
            .values(
                owner_id=self._lock_owner_id,
                acquired_at=now,
            )
        )

        if update_result.rowcount > 0:
            # Successfully claimed a stale lock - flush to ensure visibility
            await self.db.flush()
            logger.debug(
                f"Acquired planner lock by claiming stale (owner={self._lock_owner_id})"
            )
            return

        # STEP 2: No stale lock to claim, try INSERT (no lock exists yet)
        lock = PlannerLock(
            lock_key=PLANNER_LOCK_KEY,
            owner_id=self._lock_owner_id,
            acquired_at=now,
        )
        self.db.add(lock)

        try:
            await self.db.flush()
            logger.debug(
                f"Acquired planner lock via insert (owner={self._lock_owner_id})"
            )
        except IntegrityError:
            await self.db.rollback()
            # Lock already held by another tick (and it's not stale)
            existing = await self.db.execute(
                select(PlannerLock).where(PlannerLock.lock_key == PLANNER_LOCK_KEY)
            )
            existing_lock = existing.scalar_one_or_none()
            if existing_lock:
                raise PlannerLockError(
                    f"Planner tick already in progress (started at {existing_lock.acquired_at}, "
                    f"owner={existing_lock.owner_id})"
                )
            raise PlannerLockError("Failed to acquire planner lock")

    async def _release_lock(self) -> None:
        """Release the planner lock."""
        try:
            await self.db.execute(
                delete(PlannerLock).where(
                    and_(
                        PlannerLock.lock_key == PLANNER_LOCK_KEY,
                        PlannerLock.owner_id == self._lock_owner_id,
                    )
                )
            )
            await self.db.commit()
            logger.debug(f"Released planner lock (owner={self._lock_owner_id})")
        except Exception as e:
            logger.warning(f"Failed to release planner lock: {e}")

    # =========================================================================
    # EXECUTOR GATE
    # =========================================================================

    async def _has_active_execution(self) -> bool:
        """Check if there's an active execution (hard gate for running only).

        Returns True if ANY of:
        - A ticket is in EXECUTING state
        - A ticket is in VERIFYING state

        Note: We DON'T block on QUEUED jobs - this allows the planner to
        queue all planned tickets, while still respecting that only one
        ticket should be actively executing at a time.
        """
        # Check for executing or verifying tickets
        active_ticket_result = await self.db.execute(
            select(Ticket.id)
            .where(
                Ticket.state.in_(
                    [
                        TicketState.EXECUTING.value,
                        TicketState.VERIFYING.value,
                    ]
                )
            )
            .limit(1)
        )
        if active_ticket_result.scalar_one_or_none():
            logger.debug("Active execution gate: ticket in executing/verifying state")
            return True

        # Check for RUNNING execute jobs only (not queued)
        running_job_result = await self.db.execute(
            select(Job.id)
            .where(
                and_(
                    Job.kind == JobKind.EXECUTE.value,
                    Job.status == JobStatus.RUNNING.value,
                )
            )
            .limit(1)
        )
        if running_job_result.scalar_one_or_none():
            logger.debug("Active execution gate: execute job running")
            return True

        return False

    # =========================================================================
    # PICK AND EXECUTE
    # =========================================================================

    async def _pick_and_execute_next(self) -> list[tuple[PlannerAction, str | None]]:
        """Queue the SINGLE highest-priority planned ticket for execution.

        Policy:
        - Only one ticket can be actively executing at a time (enforced by _has_active_execution)
        - Only ONE ticket is queued at a time - no new jobs if any QUEUED execute jobs exist
        - This ensures Celery always executes highest priority tickets first
        - Tickets blocked by incomplete dependencies are moved to BLOCKED state

        NOTE: This only creates job rows. Celery enqueueing happens AFTER commit.

        Returns:
            List of tuples (PlannerAction, job_id) - will have 0 or 1 elements.
        """
        results: list[tuple[PlannerAction, str | None]] = []

        # Check if there are ANY queued or running execute jobs
        # If so, don't queue anything new - wait for the current job to complete
        active_job_result = await self.db.execute(
            select(Job.id)
            .where(
                and_(
                    Job.kind == JobKind.EXECUTE.value,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            )
            .limit(1)
        )
        if active_job_result.scalar_one_or_none():
            logger.debug(
                "Execute job already queued or running, not queuing new tickets"
            )
            return results

        # Find planned tickets ordered by priority
        # We need to check multiple in case the first ones are blocked
        planned_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.PLANNED.value)
            .options(selectinload(Ticket.blocked_by))  # Load blocker relationship
            .order_by(
                Ticket.priority.desc().nulls_last(),
                Ticket.created_at.asc(),
            )
            .limit(10)  # Check up to 10 tickets
        )
        planned_tickets = list(planned_result.scalars().all())

        if not planned_tickets:
            logger.info("No planned tickets to queue")
            return results

        # Find the first ticket that is NOT blocked by an incomplete dependency
        selected_ticket = None
        for ticket in planned_tickets:
            if ticket.blocked_by_ticket_id:
                # Check if the blocker is done
                if (
                    ticket.blocked_by
                    and ticket.blocked_by.state == TicketState.DONE.value
                ):
                    # Blocker is done, this ticket can be executed
                    selected_ticket = ticket
                    logger.info(
                        f"Ticket {ticket.id} was blocked by {ticket.blocked_by_ticket_id} "
                        f"but blocker is now DONE, can proceed"
                    )
                    break
                else:
                    # Blocker is not done, move ticket to BLOCKED state
                    blocker_title = (
                        ticket.blocked_by.title if ticket.blocked_by else "unknown"
                    )
                    logger.info(
                        f"Ticket {ticket.id} is blocked by incomplete ticket "
                        f"{ticket.blocked_by_ticket_id} ({blocker_title}), moving to BLOCKED"
                    )
                    ticket.state = TicketState.BLOCKED.value

                    # Create event for the transition
                    event = TicketEvent(
                        ticket_id=ticket.id,
                        event_type=EventType.TRANSITIONED.value,
                        from_state=TicketState.PLANNED.value,
                        to_state=TicketState.BLOCKED.value,
                        actor_type=ActorType.PLANNER.value,
                        actor_id="planner",
                        reason=f"Blocked by incomplete ticket: {blocker_title}",
                        payload_json=json.dumps(
                            {
                                "blocked_by_ticket_id": ticket.blocked_by_ticket_id,
                                "blocked_by_title": blocker_title,
                            }
                        ),
                    )
                    self.db.add(event)
                    # Continue to check next ticket
            else:
                # No blocker, can be executed
                selected_ticket = ticket
                break

        if not selected_ticket:
            logger.info("All planned tickets are blocked by dependencies")
            return results

        # Create execute job (do NOT enqueue Celery yet)
        # Inherit board_id from ticket for permission scoping
        job = Job(
            ticket_id=selected_ticket.id,
            board_id=selected_ticket.board_id,
            kind=JobKind.EXECUTE.value,
            status=JobStatus.QUEUED.value,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        # Create event for the action
        event = TicketEvent(
            ticket_id=selected_ticket.id,
            event_type=EventType.COMMENT.value,
            from_state=selected_ticket.state,
            to_state=selected_ticket.state,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason="Planner enqueued execute job (queue position: 1)",
            payload_json=json.dumps(
                {
                    "action": "enqueued_execute",
                    "job_id": job.id,
                    "queue_position": 1,
                }
            ),
        )
        self.db.add(event)

        logger.info(
            f"Planner created execute job {job.id} for ticket {selected_ticket.id} "
            f"(priority: {selected_ticket.priority})"
        )

        results.append(
            (
                PlannerAction(
                    action_type=PlannerActionType.ENQUEUED_EXECUTE,
                    ticket_id=selected_ticket.id,
                    ticket_title=selected_ticket.title,
                    details={"job_id": job.id, "queue_position": 1},
                ),
                job.id,
            )
        )

        return results

    async def _queue_all_planned_tickets(
        self,
    ) -> list[tuple[PlannerAction, str | None]]:
        """Queue ALL planned tickets for execution in priority order.

        Used by /planner/start to queue the entire backlog at once.
        Tickets are ordered by priority (highest first), then by created_at (oldest first).
        Tickets blocked by incomplete dependencies are moved to BLOCKED state.

        NOTE: This only creates job rows. Celery enqueueing happens AFTER commit.

        Returns:
            List of tuples (PlannerAction, job_id) for each queued ticket.
        """
        results: list[tuple[PlannerAction, str | None]] = []

        # Find ALL planned tickets ordered by priority, with blocker relationship loaded
        planned_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.PLANNED.value)
            .options(selectinload(Ticket.blocked_by))  # Load blocker relationship
            .order_by(
                Ticket.priority.desc().nulls_last(),
                Ticket.created_at.asc(),
            )
        )
        planned_tickets = list(planned_result.scalars().all())

        if not planned_tickets:
            logger.info("No planned tickets to queue")
            return results

        # Check which tickets already have queued jobs to avoid duplicates
        ticket_ids = [t.id for t in planned_tickets]
        existing_jobs_result = await self.db.execute(
            select(Job.ticket_id).where(
                and_(
                    Job.ticket_id.in_(ticket_ids),
                    Job.kind == JobKind.EXECUTE.value,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            )
        )
        already_queued = set(existing_jobs_result.scalars().all())

        # Queue each ticket that doesn't already have a job and is not blocked
        queue_position = 0
        blocked_count = 0
        for ticket in planned_tickets:
            if ticket.id in already_queued:
                logger.debug(f"Ticket {ticket.id} already has a queued job, skipping")
                continue

            # Check if ticket is blocked by an incomplete dependency
            if ticket.blocked_by_ticket_id:
                if (
                    ticket.blocked_by
                    and ticket.blocked_by.state == TicketState.DONE.value
                ):
                    # Blocker is done, this ticket can be queued
                    logger.info(
                        f"Ticket {ticket.id} was blocked by {ticket.blocked_by_ticket_id} "
                        f"but blocker is now DONE, can proceed"
                    )
                else:
                    # Blocker is not done, move ticket to BLOCKED state
                    blocker_title = (
                        ticket.blocked_by.title if ticket.blocked_by else "unknown"
                    )
                    logger.info(
                        f"Ticket {ticket.id} is blocked by incomplete ticket "
                        f"{ticket.blocked_by_ticket_id} ({blocker_title}), moving to BLOCKED"
                    )
                    ticket.state = TicketState.BLOCKED.value
                    blocked_count += 1

                    # Create event for the transition
                    event = TicketEvent(
                        ticket_id=ticket.id,
                        event_type=EventType.TRANSITIONED.value,
                        from_state=TicketState.PLANNED.value,
                        to_state=TicketState.BLOCKED.value,
                        actor_type=ActorType.PLANNER.value,
                        actor_id="planner",
                        reason=f"Blocked by incomplete ticket: {blocker_title}",
                        payload_json=json.dumps(
                            {
                                "blocked_by_ticket_id": ticket.blocked_by_ticket_id,
                                "blocked_by_title": blocker_title,
                            }
                        ),
                    )
                    self.db.add(event)
                    continue  # Skip to next ticket

            queue_position += 1

            # Create execute job
            job = Job(
                ticket_id=ticket.id,
                board_id=ticket.board_id,
                kind=JobKind.EXECUTE.value,
                status=JobStatus.QUEUED.value,
            )
            self.db.add(job)
            await self.db.flush()
            await self.db.refresh(job)

            # Create event
            event = TicketEvent(
                ticket_id=ticket.id,
                event_type=EventType.COMMENT.value,
                from_state=ticket.state,
                to_state=ticket.state,
                actor_type=ActorType.PLANNER.value,
                actor_id="planner",
                reason=f"Planner enqueued execute job (queue position: {queue_position})",
                payload_json=json.dumps(
                    {
                        "action": "enqueued_execute",
                        "job_id": job.id,
                        "queue_position": queue_position,
                    }
                ),
            )
            self.db.add(event)

            logger.info(
                f"Planner created execute job {job.id} for ticket {ticket.id} "
                f"(priority: {ticket.priority}, queue position: {queue_position})"
            )

            results.append(
                (
                    PlannerAction(
                        action_type=PlannerActionType.ENQUEUED_EXECUTE,
                        ticket_id=ticket.id,
                        ticket_title=ticket.title,
                        details={"job_id": job.id, "queue_position": queue_position},
                    ),
                    job.id,
                )
            )

        logger.info(
            f"Queued {len(results)} planned tickets for execution, "
            f"{blocked_count} moved to BLOCKED due to dependencies"
        )
        return results

    async def _unblock_ready_tickets(self) -> list[PlannerAction]:
        """Check BLOCKED tickets and unblock those whose blockers are now done.

        This method runs during each tick to automatically transition tickets
        from BLOCKED back to PLANNED when their blocking dependency is completed.

        Returns:
            List of PlannerActions for tickets that were unblocked.
        """
        actions: list[PlannerAction] = []

        # Find all BLOCKED tickets that have a blocked_by_ticket_id
        blocked_result = await self.db.execute(
            select(Ticket)
            .where(
                and_(
                    Ticket.state == TicketState.BLOCKED.value,
                    Ticket.blocked_by_ticket_id.isnot(None),
                )
            )
            .options(selectinload(Ticket.blocked_by))
        )
        blocked_tickets = list(blocked_result.scalars().all())

        for ticket in blocked_tickets:
            # Check if the blocker is now done
            if ticket.blocked_by and ticket.blocked_by.state == TicketState.DONE.value:
                # Unblock: transition from BLOCKED to PLANNED
                logger.info(
                    f"Unblocking ticket {ticket.id}: blocker {ticket.blocked_by_ticket_id} "
                    f"is now DONE"
                )
                old_state = ticket.state
                ticket.state = TicketState.PLANNED.value

                # Create event for the transition
                event = TicketEvent(
                    ticket_id=ticket.id,
                    event_type=EventType.TRANSITIONED.value,
                    from_state=old_state,
                    to_state=TicketState.PLANNED.value,
                    actor_type=ActorType.PLANNER.value,
                    actor_id="planner",
                    reason=f"Unblocked: blocking ticket '{ticket.blocked_by.title}' is now done",
                    payload_json=json.dumps(
                        {
                            "blocker_ticket_id": ticket.blocked_by_ticket_id,
                            "blocker_title": ticket.blocked_by.title,
                            "action": "unblocked",
                        }
                    ),
                )
                self.db.add(event)

                actions.append(
                    PlannerAction(
                        action_type="unblocked",
                        ticket_id=ticket.id,
                        ticket_title=ticket.title,
                        details={
                            "blocker_ticket_id": ticket.blocked_by_ticket_id,
                            "blocker_title": ticket.blocked_by.title,
                        },
                    )
                )

                # Clear the dependency FK so UI stops showing the badge
                ticket.blocked_by_ticket_id = None

        if actions:
            logger.info(f"Unblocked {len(actions)} tickets")

        return actions

    async def _enqueue_celery_job(self, job_id: str) -> None:
        """Enqueue a Celery task for a job (called AFTER commit).

        This method is designed to be idempotent and failure-tolerant:
        - If the Celery task fails to enqueue, the job watchdog will recover it
        - If the DB update fails after Celery enqueue, the task ID is lost but
          the watchdog will re-enqueue (Celery task deduplicates by job_id)
        """
        from app.services.task_dispatch import enqueue_task

        try:
            # Re-fetch the job to update task ID
            result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                logger.error(f"Job {job_id} not found when enqueueing task")
                return

            # Skip if job already has a task ID (idempotency)
            if job.celery_task_id:
                logger.debug(f"Job {job_id} already has task {job.celery_task_id}")
                return

            # Enqueue the task via unified dispatch
            task = enqueue_task("execute_ticket", args=[job_id])
            job.celery_task_id = task.id
            await self.db.commit()

            logger.info(f"Enqueued task {task.id} for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to enqueue Celery task for job {job_id}: {e}")
            # Don't re-raise - the watchdog will recover this job
            # Rolling back to ensure clean session state
            await self.db.rollback()

    # =========================================================================
    # BLOCKED TICKET HANDLING (with caps)
    # =========================================================================

    async def _handle_blocked_tickets(self) -> list[PlannerAction]:
        """Generate follow-up proposals for blocked tickets.

        Enforces caps:
        - max_followups_per_ticket: Skip tickets that already have this many follow-ups
        - max_followups_per_tick: Stop creating follow-ups after this limit
        - skip_followup_reasons: Skip certain blocker reasons

        Returns:
            List of PlannerActions for follow-ups created.
        """
        actions: list[PlannerAction] = []
        followups_created_this_tick = 0

        # Find blocked tickets
        blocked_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.BLOCKED.value)
            .options(selectinload(Ticket.goal), selectinload(Ticket.events))
        )
        blocked_tickets = blocked_result.scalars().all()

        for ticket in blocked_tickets:
            # Cap: max follow-ups per tick
            if followups_created_this_tick >= self.config.max_followups_per_tick:
                logger.debug(
                    f"Hit max_followups_per_tick ({self.config.max_followups_per_tick}), stopping"
                )
                break

            # Cap: count existing follow-ups for this ticket
            existing_followup_count = sum(
                1
                for event in ticket.events
                if event.payload_json and FOLLOWUP_MARKER in event.payload_json
            )
            if existing_followup_count >= self.config.max_followups_per_ticket:
                logger.debug(
                    f"Ticket {ticket.id} already has {existing_followup_count} follow-ups "
                    f"(max {self.config.max_followups_per_ticket}), skipping"
                )
                continue

            # Get the blocker reason and payload from the most recent blocking event
            blocker_reason = None
            blocker_payload = {}
            for event in reversed(ticket.events):
                if event.to_state == TicketState.BLOCKED.value and event.reason:
                    blocker_reason = event.reason
                    if event.payload_json:
                        try:
                            blocker_payload = json.loads(event.payload_json)
                        except (json.JSONDecodeError, TypeError):
                            blocker_payload = {}
                    break

            # Skip: tickets with skip_followup flag (no changes needed)
            if blocker_payload.get("skip_followup"):
                logger.debug(
                    f"Skipping follow-up for ticket {ticket.id}: "
                    f"skip_followup flag is set (no changes needed)"
                )
                continue

            # Skip: tickets that already have a manual work follow-up
            if blocker_payload.get("manual_work_followup_id"):
                logger.debug(
                    f"Skipping follow-up for ticket {ticket.id}: "
                    f"already has manual work follow-up {blocker_payload.get('manual_work_followup_id')}"
                )
                continue

            # Skip: certain blocker reasons should not trigger follow-ups
            if blocker_reason and self._should_skip_followup(blocker_reason):
                logger.debug(
                    f"Skipping follow-up for ticket {ticket.id}: "
                    f"blocker reason '{blocker_reason}' is in skip list"
                )
                continue

            # Fetch sibling ticket titles in the same goal to avoid duplicates
            sibling_titles: list[str] = []
            if ticket.goal_id:
                sibling_result = await self.db.execute(
                    select(Ticket.title).where(
                        and_(
                            Ticket.goal_id == ticket.goal_id,
                            Ticket.id != ticket.id,
                        )
                    )
                )
                sibling_titles = [row[0] for row in sibling_result.fetchall()]

            # Generate follow-up proposal using LLM
            try:
                proposal = await self._generate_followup_proposal(
                    ticket_title=ticket.title,
                    ticket_description=ticket.description,
                    blocker_reason=blocker_reason,
                    goal_title=ticket.goal.title if ticket.goal else None,
                    goal_description=ticket.goal.description if ticket.goal else None,
                    existing_ticket_titles=sibling_titles,
                )
            except Exception as e:
                logger.error(
                    f"Failed to generate follow-up for ticket {ticket.id}: {e}"
                )
                continue

            # Determine initial state: auto-approve if goal has autonomy enabled
            initial_state = TicketState.PROPOSED.value
            auto_approved_followup = False
            try:
                goal = ticket.goal
                if goal and goal.autonomy_enabled and goal.auto_approve_followups:
                    initial_state = TicketState.PLANNED.value
                    auto_approved_followup = True
            except Exception:
                pass

            # Create follow-up ticket
            followup_ticket = Ticket(
                goal_id=ticket.goal_id,
                board_id=ticket.board_id,
                title=proposal.title,
                description=proposal.description,
                state=initial_state,
                priority=ticket.priority,  # Inherit priority
            )
            self.db.add(followup_ticket)
            await self.db.flush()
            await self.db.refresh(followup_ticket)

            # Create creation event for follow-up ticket (with parent link)
            creation_event = TicketEvent(
                ticket_id=followup_ticket.id,
                event_type=EventType.CREATED.value,
                from_state=None,
                to_state=initial_state,
                actor_type=ActorType.PLANNER.value,
                actor_id="planner",
                reason=f"Follow-up for blocked ticket: {ticket.title}",
                payload_json=json.dumps(
                    {
                        "parent_ticket_id": ticket.id,  # Link to blocked ticket
                        "blocked_ticket_id": ticket.id,  # Legacy field
                        "verification": proposal.verification,
                        "auto_approved": auto_approved_followup,
                    }
                ),
            )
            self.db.add(creation_event)

            # Record autonomy event if auto-approved
            if auto_approved_followup:
                autonomy_event = TicketEvent(
                    ticket_id=followup_ticket.id,
                    event_type=EventType.TRANSITIONED.value,
                    from_state=TicketState.PROPOSED.value,
                    to_state=TicketState.PLANNED.value,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id="autonomy_service",
                    reason="Auto-approved follow-up ticket (autonomy mode)",
                    payload_json=json.dumps({"autonomy_action": "approve_followup"}),
                )
                self.db.add(autonomy_event)

            # Create event on blocked ticket noting the follow-up
            link_event = TicketEvent(
                ticket_id=ticket.id,
                event_type=EventType.COMMENT.value,
                from_state=ticket.state,
                to_state=ticket.state,
                actor_type=ActorType.PLANNER.value,
                actor_id="planner",
                reason=f"Created follow-up ticket: {followup_ticket.title}",
                payload_json=json.dumps(
                    {
                        FOLLOWUP_MARKER: True,
                        "followup_ticket_id": followup_ticket.id,
                    }
                ),
            )
            self.db.add(link_event)

            followups_created_this_tick += 1
            logger.info(
                f"Created follow-up ticket {followup_ticket.id} for blocked ticket {ticket.id}"
            )

            add_orchestrator_log(
                "INFO",
                f"Follow-up created: '{proposal.title}'",
                {
                    "followup_ticket_id": followup_ticket.id,
                    "blocked_ticket_id": ticket.id,
                    "blocked_ticket_title": ticket.title,
                    "blocker_reason": blocker_reason,
                    "existing_siblings": len(sibling_titles),
                },
            )

            actions.append(
                PlannerAction(
                    action_type=PlannerActionType.PROPOSED_FOLLOWUP,
                    ticket_id=ticket.id,
                    ticket_title=ticket.title,
                    details={
                        "followup_ticket_id": followup_ticket.id,
                        "followup_title": proposal.title,
                        "parent_ticket_id": ticket.id,
                    },
                )
            )

        return actions

    async def _generate_followup_proposal(
        self,
        ticket_title: str,
        ticket_description: str | None,
        blocker_reason: str | None,
        goal_title: str | None = None,
        goal_description: str | None = None,
        existing_ticket_titles: list[str] | None = None,
    ) -> FollowUpProposal:
        """Generate a follow-up ticket proposal for a blocked ticket using LLM.

        Uses asyncio.to_thread() to avoid blocking the event loop during LLM calls.
        """
        import asyncio

        context_parts = []
        if goal_title:
            context_parts.append(f"Goal: {goal_title}")
        if goal_description:
            context_parts.append(f"Goal description: {goal_description}")
        context_parts.append(f"Blocked ticket: {ticket_title}")
        if ticket_description:
            context_parts.append(f"Ticket description: {ticket_description}")
        if blocker_reason:
            context_parts.append(f"Blocker reason: {blocker_reason}")

        # Include existing tickets so LLM avoids duplicates
        existing_section = ""
        if existing_ticket_titles:
            ticket_list = "\n".join(f"- {t}" for t in existing_ticket_titles)
            existing_section = f"""

## Existing Tickets (DO NOT DUPLICATE)
These tickets already exist in the same goal. Do NOT create a follow-up that overlaps with any of these:
{ticket_list}"""

        context = "\n".join(context_parts)

        system_prompt = """You are a technical project planner. Given a blocked ticket, propose a follow-up ticket that addresses the blocker.

Your response MUST be valid JSON with this exact structure:
{
  "title": "Short, actionable title for the follow-up ticket",
  "description": "Clear description of what needs to be done to unblock the original ticket",
  "verification": ["command1", "command2"]
}

Guidelines:
- The title should be concise and action-oriented
- The description should explain what specifically needs to be done
- Verification commands should be shell commands that can verify the follow-up is complete
- Focus on the immediate blocker, not the entire original ticket
- Do NOT create a ticket that duplicates an existing one"""

        user_prompt = f"""A ticket is blocked and needs a follow-up ticket to address the blocker.

{context}{existing_section}

Generate a follow-up ticket proposal as JSON."""

        def _blocking_llm_call():
            """Execute blocking LLM call in thread pool."""
            return self.llm_service.call_completion(
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=self.config.max_tokens_followup,
                system_prompt=system_prompt,
            )

        try:
            # Run blocking LLM call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(_blocking_llm_call)
            data = self.llm_service.safe_parse_json(response.content, {})

            return FollowUpProposal(
                title=data.get("title", "Follow-up for blocked ticket"),
                description=data.get(
                    "description", "Address the blocker from the original ticket."
                ),
                verification=data.get("verification", []),
            )
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            # Return a fallback proposal
            return FollowUpProposal(
                title=f"Follow-up: {ticket_title}",
                description=f"Address blocker: {blocker_reason or 'Unknown blocker'}",
                verification=[],
            )

    def _should_skip_followup(self, blocker_reason: str) -> bool:
        """Check if this blocker reason should skip follow-up generation."""
        reason_lower = blocker_reason.lower()
        for skip_reason in self.config.skip_followup_reasons:
            if skip_reason.lower() in reason_lower:
                return True
        return False

    # =========================================================================
    # REFLECTION GENERATION
    # =========================================================================

    async def _generate_reflections(self) -> list[PlannerAction]:
        """Generate reflection summaries for completed tickets.

        Reflections are stored as TicketEvents (type=COMMENT), never in ticket text.
        This keeps ticket data clean and reflections as evidence.

        Returns:
            List of PlannerActions for reflections generated.
        """
        actions: list[PlannerAction] = []

        # Find done tickets
        done_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.DONE.value)
            .options(selectinload(Ticket.events), selectinload(Ticket.evidence))
        )
        done_tickets = done_result.scalars().all()

        for ticket in done_tickets:
            # Check if this ticket already has a reflection
            has_reflection = any(
                event.payload_json and REFLECTION_MARKER in event.payload_json
                for event in ticket.events
            )

            if has_reflection:
                logger.debug(f"Ticket {ticket.id} already has a reflection")
                continue

            # Build events summary
            events_summary = self._summarize_events(ticket.events)

            # Build evidence summary
            evidence_summary = self._summarize_evidence(ticket.evidence)

            # Generate reflection using LLM
            try:
                reflection = await self._generate_reflection_summary(
                    ticket_title=ticket.title,
                    ticket_description=ticket.description,
                    events_summary=events_summary,
                    evidence_summary=evidence_summary,
                )
            except Exception as e:
                logger.error(
                    f"Failed to generate reflection for ticket {ticket.id}: {e}"
                )
                continue

            # Create reflection event (NEVER modify ticket text)
            reflection_event = TicketEvent(
                ticket_id=ticket.id,
                event_type=REFLECTION_EVENT_TYPE,
                from_state=ticket.state,
                to_state=ticket.state,
                actor_type=ActorType.PLANNER.value,
                actor_id="planner",
                reason=reflection.summary,
                payload_json=json.dumps(
                    {
                        REFLECTION_MARKER: True,
                        "type": "reflection_added",
                    }
                ),
            )
            self.db.add(reflection_event)

            logger.info(f"Generated reflection for ticket {ticket.id}")

            actions.append(
                PlannerAction(
                    action_type=PlannerActionType.GENERATED_REFLECTION,
                    ticket_id=ticket.id,
                    ticket_title=ticket.title,
                    details={"summary": reflection.summary},
                )
            )

        return actions

    async def _auto_merge_done_tickets(self) -> list[PlannerAction]:
        """Auto-merge DONE tickets where goal has auto_merge enabled.

        Scans for DONE tickets whose goals have autonomy_enabled + auto_merge,
        and where a workspace still exists (not yet merged).

        Returns:
            List of PlannerActions for merge results.
        """
        from app.services.merge_service import MergeService

        actions: list[PlannerAction] = []

        # Find DONE tickets with active workspaces
        done_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.DONE.value)
            .options(
                selectinload(Ticket.workspace),
                selectinload(Ticket.goal),
                selectinload(Ticket.revisions),
                selectinload(Ticket.events),
            )
        )
        done_tickets = done_result.scalars().all()

        for ticket in done_tickets:
            # Skip if no active workspace (already merged or cleaned up)
            if not ticket.workspace or not ticket.workspace.is_active:
                continue

            # Skip if goal doesn't have auto_merge enabled
            goal = ticket.goal
            if not goal or not goal.autonomy_enabled or not goal.auto_merge:
                continue

            # Skip if already merged (check events)
            already_merged = any(
                e.event_type == EventType.MERGE_SUCCEEDED.value for e in ticket.events
            )
            if already_merged:
                continue

            # Skip if no approved revision
            from app.models.revision import RevisionStatus

            has_approved = any(
                r.status == RevisionStatus.APPROVED.value for r in ticket.revisions
            )
            if not has_approved:
                # Auto-approve the latest open revision if autonomy allows it
                open_revision = next(
                    (r for r in ticket.revisions if r.status == "open"),
                    None,
                )
                if open_revision:
                    open_revision.status = RevisionStatus.APPROVED.value
                    await self.db.flush()
                    logger.info(
                        f"Auto-approved revision {open_revision.id} for ticket {ticket.id}"
                    )
                else:
                    continue

            try:
                merge_service = MergeService(self.db)
                merge_result = await merge_service.merge_ticket(
                    ticket_id=ticket.id,
                    actor_id="autonomy_service",
                )

                if merge_result.success:
                    actions.append(
                        PlannerAction(
                            action_type=PlannerActionType.SKIPPED,  # No specific merge type exists
                            ticket_id=ticket.id,
                            ticket_title=ticket.title,
                            details={
                                "action": "auto_merge",
                                "success": True,
                                "message": merge_result.message,
                            },
                        )
                    )
                    logger.info(
                        f"Auto-merged ticket {ticket.id}: {merge_result.message}"
                    )
                else:
                    # Transition to BLOCKED on merge failure
                    ticket.state = TicketState.BLOCKED.value
                    blocked_event = TicketEvent(
                        ticket_id=ticket.id,
                        event_type=EventType.TRANSITIONED.value,
                        from_state=TicketState.DONE.value,
                        to_state=TicketState.BLOCKED.value,
                        actor_type=ActorType.SYSTEM.value,
                        actor_id="autonomy_service",
                        reason=f"Auto-merge failed: {merge_result.message}",
                        payload_json=json.dumps(
                            {
                                "autonomy_action": "auto_merge_failed",
                                "merge_error": merge_result.message,
                            }
                        ),
                    )
                    self.db.add(blocked_event)
                    logger.warning(
                        f"Auto-merge failed for ticket {ticket.id}: {merge_result.message}"
                    )

            except Exception as e:
                logger.error(f"Auto-merge error for ticket {ticket.id}: {e}")

        return actions

    async def _udar_incremental_replan(self) -> list[PlannerAction]:
        """UDAR incremental replanning: analyze completed tickets and generate follow-ups.

        COST OPTIMIZATION:
        - Batches tickets (waits for 5 tickets before analyzing)
        - Only calls LLM if changes significant (>10 files OR verification failed)
        - Target: 1 LLM call per 5 completed tickets (or 0 if minor changes)

        Returns:
            List of PlannerActions for follow-ups generated.
        """
        from datetime import datetime, timedelta

        from app.services.udar_planner_service import UDARPlannerService

        actions: list[PlannerAction] = []

        # Find recently completed tickets (last 30 minutes, not yet analyzed)
        # Note: We track analyzed status in ticket metadata
        recent_cutoff = datetime.utcnow() - timedelta(minutes=30)
        done_result = await self.db.execute(
            select(Ticket).where(
                Ticket.state == TicketState.DONE.value,
                Ticket.updated_at >= recent_cutoff,
            )
        )
        recent_done = done_result.scalars().all()

        # Filter to only unanalyzed tickets
        unanalyzed = [
            t
            for t in recent_done
            if not (t.metadata_ and t.metadata_.get("udar_analyzed_at"))
        ]

        if not unanalyzed:
            logger.debug("No unanalyzed completed tickets for UDAR replanning")
            return actions

        # Check if batch size reached (from config)
        # This prevents frequent small LLM calls
        batch_size = self.config.udar.replan_batch_size
        if len(unanalyzed) < batch_size:
            logger.debug(
                f"UDAR replanning: Only {len(unanalyzed)} tickets, waiting for batch of {batch_size}"
            )
            return actions

        # Take up to batch_size tickets for analysis
        tickets_to_analyze = unanalyzed[:batch_size]
        ticket_ids = [t.id for t in tickets_to_analyze]

        logger.info(
            f"UDAR replanning: Analyzing batch of {len(ticket_ids)} completed tickets"
        )

        # Call UDAR agent for batched replanning
        udar_service = UDARPlannerService(self.db)
        try:
            result = await udar_service.replan_after_completion(ticket_ids)

            logger.info(
                f"UDAR replanning: {result['summary']} "
                f"(LLM calls: {result['llm_calls_made']})"
            )

            # Mark tickets as analyzed to avoid duplicate analysis
            for ticket in tickets_to_analyze:
                if not ticket.metadata_:
                    ticket.metadata_ = {}
                ticket.metadata_["udar_analyzed_at"] = datetime.utcnow().isoformat()
                ticket.metadata_["udar_batch_id"] = ticket_ids[0]  # Track batch

            # Create PlannerActions for created follow-ups
            if result["follow_ups_created"] > 0:
                actions.append(
                    PlannerAction(
                        action_type=PlannerActionType.PROPOSED_FOLLOWUP,
                        ticket_id=ticket_ids[0],  # Reference first ticket in batch
                        ticket_title=f"Batch of {len(ticket_ids)} tickets",
                        details={
                            "follow_ups_created": result["follow_ups_created"],
                            "tickets_analyzed": result["tickets_analyzed"],
                            "significant_tickets": result["significant_tickets"],
                            "llm_calls": result["llm_calls_made"],
                            "batch_size": len(ticket_ids),
                        },
                    )
                )

        except Exception as e:
            logger.error(f"UDAR replanning failed: {e}")
            # Don't fail the entire tick, just log the error

        return actions

    async def _generate_reflection_summary(
        self,
        ticket_title: str,
        ticket_description: str | None,
        events_summary: str | None = None,
        evidence_summary: str | None = None,
    ) -> ReflectionSummary:
        """Generate a reflection summary for a completed ticket using LLM.

        Uses asyncio.to_thread() to avoid blocking the event loop during LLM calls.
        """
        import asyncio

        context_parts = [f"Ticket: {ticket_title}"]
        if ticket_description:
            context_parts.append(f"Description: {ticket_description}")
        if events_summary:
            context_parts.append(f"Journey: {events_summary}")
        if evidence_summary:
            context_parts.append(f"Evidence: {evidence_summary}")

        context = "\n".join(context_parts)

        system_prompt = """You are a technical project assistant. Generate a brief reflection summary for a completed ticket.

Your response MUST be valid JSON with this exact structure:
{
  "summary": "A concise 2-3 sentence reflection on what was accomplished and any lessons learned"
}

Guidelines:
- Keep it brief and factual
- Highlight what was achieved
- Note any interesting patterns or challenges overcome
- Write in past tense"""

        user_prompt = f"""A ticket has been completed. Generate a reflection summary.

{context}

Generate a reflection summary as JSON."""

        def _blocking_llm_call():
            """Execute blocking LLM call in thread pool."""
            return self.llm_service.call_completion(
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=self.config.max_tokens_reflection,
                system_prompt=system_prompt,
            )

        try:
            # Run blocking LLM call in thread pool to avoid blocking event loop
            response = await asyncio.to_thread(_blocking_llm_call)
            data = self.llm_service.safe_parse_json(response.content, {})

            return ReflectionSummary(
                summary=data.get("summary", f"Completed: {ticket_title}"),
            )
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            # Return a fallback summary
            return ReflectionSummary(
                summary=f"Ticket '{ticket_title}' was completed successfully.",
            )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _summarize_events(self, events: list[TicketEvent]) -> str:
        """Summarize ticket events for context."""
        if not events:
            return "No events"

        transitions = []
        for event in events:
            if event.event_type == EventType.TRANSITIONED.value:
                transitions.append(f"{event.from_state} → {event.to_state}")
            elif event.event_type == EventType.CREATED.value:
                transitions.append(f"created ({event.to_state})")

        if transitions:
            return " → ".join(transitions[:5])  # Limit to first 5 transitions
        return "No state transitions"

    def _summarize_evidence(self, evidence: list) -> str:
        """Summarize verification evidence for context."""
        if not evidence:
            return "No verification evidence"

        passed = sum(1 for e in evidence if e.succeeded)
        failed = len(evidence) - passed

        parts = []
        if passed:
            parts.append(f"{passed} passed")
        if failed:
            parts.append(f"{failed} failed")

        return ", ".join(parts) if parts else "No evidence"

    def _generate_summary(self, actions: list[PlannerAction]) -> str:
        """Generate a human-readable summary of actions taken."""
        if not actions:
            return "No actions taken. Board is stable."

        # Filter out SKIPPED actions for the main summary
        real_actions = [
            a for a in actions if a.action_type != PlannerActionType.SKIPPED
        ]
        skipped_actions = [
            a for a in actions if a.action_type == PlannerActionType.SKIPPED
        ]

        if not real_actions:
            if skipped_actions:
                reasons = [
                    a.details.get("reason", "unknown") if a.details else "unknown"
                    for a in skipped_actions
                ]
                return f"No actions taken. Skipped: {'; '.join(reasons)}"
            return "No actions taken. Board is stable."

        parts = []

        # Count actions by type
        executes = [
            a
            for a in real_actions
            if a.action_type == PlannerActionType.ENQUEUED_EXECUTE
        ]
        followups = [
            a
            for a in real_actions
            if a.action_type == PlannerActionType.PROPOSED_FOLLOWUP
        ]
        reflections = [
            a
            for a in real_actions
            if a.action_type == PlannerActionType.GENERATED_REFLECTION
        ]

        if executes:
            titles = [a.ticket_title or a.ticket_id for a in executes]
            parts.append(f"Enqueued execution for: {', '.join(titles)}")

        if followups:
            parts.append(
                f"Created {len(followups)} follow-up ticket(s) for blocked items"
            )

        if reflections:
            parts.append(
                f"Generated {len(reflections)} reflection(s) for completed tickets"
            )

        return ". ".join(parts) + "."
