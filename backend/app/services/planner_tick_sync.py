"""Synchronous planner tick for Celery workers.

This module provides a synchronous implementation of the planner tick
logic that can run in Celery worker processes without async issues.

The key difference from the async PlannerService is that this uses
SQLAlchemy's synchronous Session instead of AsyncSession, avoiding
the "pysqlite is not async" error that occurs when running asyncio
code in forked Celery worker processes.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database_sync import get_sync_db
from app.models.job import Job, JobKind, JobStatus
from app.models.planner_lock import PlannerLock
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.config_service import ConfigService, PlannerConfig
from app.services.llm_service import LLMService
from app.state_machine import ActorType, EventType, TicketState

logger = logging.getLogger(__name__)

# Lock settings (same as async version)
PLANNER_LOCK_KEY = "planner_tick"
LOCK_STALE_MINUTES = 10

# Markers (same as async version)
REFLECTION_EVENT_TYPE = EventType.COMMENT.value
REFLECTION_MARKER = "planner_reflection"
FOLLOWUP_MARKER = "planner_followup_created"


class PlannerLockError(Exception):
    """Raised when planner lock cannot be acquired."""

    pass


def run_planner_tick_sync() -> dict:
    """Run a synchronous planner tick.

    This is the main entry point for Celery worker tasks.

    Returns:
        Dict with tick results: executed, followups_created, reflections_added, queued_executed

    Raises:
        PlannerLockError: If lock cannot be acquired
    """
    lock_owner_id = str(uuid.uuid4())

    # Load config
    from pathlib import Path

    kanban_root = Path(__file__).parent.parent.parent.parent
    config_service = ConfigService(repo_path=kanban_root)
    config = config_service.get_planner_config()

    executed = 0
    followups_created = 0
    reflections_added = 0
    queued_executed = 0
    jobs_to_enqueue: list[str] = []

    with get_sync_db() as db:
        # Acquire lock
        _acquire_lock_sync(db, lock_owner_id)

        try:
            # 0. Check for queued messages on tickets ready for execution
            # This enables the instant follow-up UX like vibe-kanban
            if config.features.auto_execute:
                queued_job_id = _execute_queued_message_sync(db)
                if queued_job_id:
                    jobs_to_enqueue.append(queued_job_id)
                    queued_executed = 1

            from app.services.orchestrator_log import add_orchestrator_log

            # 1. Unblock tickets whose blockers are now done
            unblocked = _unblock_ready_tickets_sync(db)
            if unblocked:
                add_orchestrator_log(
                    "INFO",
                    f"Unblocked {unblocked} ticket(s) (blockers reached DONE)",
                    {"count": unblocked},
                )

            # 2. Pick and execute planned tickets (parallel-aware)
            if config.features.auto_execute and queued_executed == 0:
                new_job_ids = _pick_and_execute_next_sync(db)
                if new_job_ids:
                    jobs_to_enqueue.extend(new_job_ids)
                    executed = len(new_job_ids)

            # 3. Handle blocked tickets (LLM-powered)
            if config.features.propose_followups:
                followups_created = _handle_blocked_tickets_sync(db, config)
                if followups_created:
                    add_orchestrator_log(
                        "INFO",
                        f"Created {followups_created} follow-up ticket(s) for blocked tickets",
                        {"count": followups_created},
                    )

            # 4. Generate reflections (LLM-powered)
            if config.features.generate_reflections:
                reflections_added = _generate_reflections_sync(db, config)
                if reflections_added:
                    add_orchestrator_log(
                        "INFO",
                        f"Generated {reflections_added} reflection(s) for done tickets",
                        {"count": reflections_added},
                    )

            # Commit all changes
            db.commit()

        finally:
            # Always release lock
            _release_lock_sync(db, lock_owner_id)

    # Enqueue Celery jobs AFTER commit
    for job_id in jobs_to_enqueue:
        _enqueue_celery_job_sync(job_id)

    return {
        "executed": executed,
        "followups_created": followups_created,
        "reflections_added": reflections_added,
        "queued_executed": queued_executed,
        "unblocked": unblocked,
    }


def _acquire_lock_sync(db, owner_id: str) -> None:
    """Acquire the planner lock synchronously."""
    stale_threshold = datetime.now(UTC) - timedelta(minutes=LOCK_STALE_MINUTES)
    now = datetime.now(UTC)

    # Try to claim a stale lock via UPDATE
    update_result = db.execute(
        update(PlannerLock)
        .where(
            and_(
                PlannerLock.lock_key == PLANNER_LOCK_KEY,
                PlannerLock.acquired_at < stale_threshold,
            )
        )
        .values(
            owner_id=owner_id,
            acquired_at=now,
        )
    )

    if update_result.rowcount > 0:
        db.flush()
        logger.debug(f"Acquired planner lock by claiming stale (owner={owner_id})")
        return

    # Try INSERT (no lock exists yet)
    lock = PlannerLock(
        lock_key=PLANNER_LOCK_KEY,
        owner_id=owner_id,
        acquired_at=now,
    )
    db.add(lock)

    try:
        db.flush()
        logger.debug(f"Acquired planner lock via insert (owner={owner_id})")
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(PlannerLock).where(PlannerLock.lock_key == PLANNER_LOCK_KEY)
        )
        existing_lock = existing.scalar_one_or_none()
        if existing_lock:
            raise PlannerLockError(
                f"Planner tick already in progress (started at {existing_lock.acquired_at})"
            )
        raise PlannerLockError("Failed to acquire planner lock")


def _release_lock_sync(db, owner_id: str) -> None:
    """Release the planner lock synchronously.

    Note: Does NOT commit - the caller's context manager handles the final commit.
    This avoids double-commit issues when called from within get_sync_db() context.
    """
    try:
        db.execute(
            delete(PlannerLock).where(
                and_(
                    PlannerLock.lock_key == PLANNER_LOCK_KEY,
                    PlannerLock.owner_id == owner_id,
                )
            )
        )
        # Don't commit here - let the context manager handle it
        # This prevents double-commit and ensures atomic behavior
        db.flush()  # Flush to ensure the delete is staged
        logger.debug(f"Released planner lock (owner={owner_id})")
    except Exception as e:
        logger.warning(f"Failed to release planner lock: {e}")


def _count_active_executions_sync(db) -> int:
    """Count active executions (queued + running execute jobs)."""
    from sqlalchemy import func as sql_func

    count = db.execute(
        select(sql_func.count(Job.id)).where(
            and_(
                Job.kind == JobKind.EXECUTE.value,
                Job.status.in_(
                    [
                        JobStatus.QUEUED.value,
                        JobStatus.RUNNING.value,
                    ]
                ),
            )
        )
    ).scalar_one()
    return count or 0


def _has_active_execution_sync(db) -> bool:
    """Check if there's an active execution (synchronous)."""
    return _count_active_executions_sync(db) > 0


def _get_max_parallel_jobs() -> int:
    """Read max_parallel_jobs from config."""
    try:
        config = ConfigService().load_config()
        return config.execute_config.max_parallel_jobs
    except Exception:
        return 1


def _unblock_ready_tickets_sync(db) -> int:
    """Check BLOCKED tickets and unblock those whose blockers are now done.

    Mirrors the async ``PlannerService._unblock_ready_tickets`` so that the
    sync periodic tick (run by SQLiteWorker) also transitions dependent
    tickets from BLOCKED → PLANNED once their blocker reaches DONE.

    Returns:
        Number of tickets that were unblocked.
    """
    blocked_tickets = (
        db.execute(
            select(Ticket)
            .where(
                and_(
                    Ticket.state == TicketState.BLOCKED.value,
                    Ticket.blocked_by_ticket_id.isnot(None),
                )
            )
            .options(selectinload(Ticket.blocked_by))
        )
        .scalars()
        .all()
    )

    unblocked = 0
    for ticket in blocked_tickets:
        if ticket.blocked_by and ticket.blocked_by.state == TicketState.DONE.value:
            logger.info(
                f"Unblocking ticket {ticket.id}: blocker {ticket.blocked_by_ticket_id} "
                f"is now DONE"
            )
            old_state = ticket.state
            ticket.state = TicketState.PLANNED.value

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
            db.add(event)

            # Clear the dependency FK so UI stops showing the badge
            ticket.blocked_by_ticket_id = None
            unblocked += 1

    if unblocked:
        db.flush()
        logger.info(f"Unblocked {unblocked} tickets")

    return unblocked


def _pick_and_execute_next_sync(db) -> list[str]:
    """Pick planned tickets and create execute jobs, respecting parallelism.

    When max_parallel_jobs > 1, picks multiple independent tickets (those not
    blocked by unfinished dependencies). Dependent tickets are always sequential.

    Returns:
        List of Job IDs that were queued (may be empty).
    """
    max_parallel = _get_max_parallel_jobs()
    active_count = _count_active_executions_sync(db)
    slots = max_parallel - active_count

    if slots <= 0:
        logger.debug(
            f"No execution slots available ({active_count}/{max_parallel} active)"
        )
        return []

    # Find planned tickets ordered by priority
    planned_tickets = (
        db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.PLANNED.value)
            .options(selectinload(Ticket.blocked_by))
            .order_by(
                Ticket.priority.desc().nulls_last(),
                Ticket.created_at.asc(),
            )
            .limit(slots * 2)  # Fetch extra in case some are dependency-blocked
        )
        .scalars()
        .all()
    )

    if not planned_tickets:
        return []

    # Collect ticket IDs that already have active jobs (avoid double-scheduling)
    active_ticket_ids = set(
        db.execute(
            select(Job.ticket_id).where(
                and_(
                    Job.kind == JobKind.EXECUTE.value,
                    Job.status.in_(
                        [
                            JobStatus.QUEUED.value,
                            JobStatus.RUNNING.value,
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )

    job_ids = []
    for ticket in planned_tickets:
        if len(job_ids) >= slots:
            break

        # Skip if already has an active job
        if ticket.id in active_ticket_ids:
            continue

        # Check dependency — push to BLOCKED if blocker isn't done
        if ticket.blocked_by_ticket_id:
            blocker = ticket.blocked_by
            if blocker is None or blocker.state != TicketState.DONE.value:
                blocker_title = blocker.title if blocker else "unknown"
                logger.info(
                    "Ticket %s blocked by incomplete %s (%s), moving to BLOCKED",
                    ticket.id,
                    ticket.blocked_by_ticket_id,
                    blocker_title,
                )
                ticket.state = TicketState.BLOCKED.value
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
                db.add(event)
                continue

        # Create execute job
        job = Job(
            ticket_id=ticket.id,
            board_id=ticket.board_id,
            kind=JobKind.EXECUTE.value,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.flush()
        db.refresh(job)

        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.COMMENT.value,
            from_state=ticket.state,
            to_state=ticket.state,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason="Planner enqueued execute job",
            payload_json=json.dumps(
                {
                    "action": "enqueued_execute",
                    "job_id": job.id,
                }
            ),
        )
        db.add(event)
        job_ids.append(job.id)

        logger.info(f"Planner created execute job {job.id} for ticket {ticket.id}")

    if job_ids:
        logger.info(
            f"Planner queued {len(job_ids)} execute job(s) "
            f"({active_count + len(job_ids)}/{max_parallel} slots used)"
        )
    return job_ids


def _execute_queued_message_sync(db) -> str | None:
    """Execute a queued follow-up message if one exists.

    Checks for tickets that:
    1. Have a queued message in Redis
    2. Are in a state ready for execution (DONE with changes_requested, BLOCKED, or NEEDS_HUMAN)
    3. Have no active jobs running

    This enables the vibe-kanban-style instant follow-up UX.

    Returns:
        Job ID if a queued message was executed, None otherwise.
    """
    from app.services.queued_message_service import queued_message_service

    # Find tickets that might have queued messages
    # These are tickets ready for re-execution after completing a cycle
    ready_tickets = (
        db.execute(
            select(Ticket).where(
                Ticket.state.in_(
                    [
                        TicketState.DONE.value,  # Approved but has queued follow-up
                        TicketState.NEEDS_HUMAN.value,  # Ready for human input (with queued message)
                        TicketState.BLOCKED.value,  # Blocked but has queued fix
                    ]
                )
            )
        )
        .scalars()
        .all()
    )

    for ticket in ready_tickets:
        # Check if this ticket has a queued message
        queued = queued_message_service.take_queued(ticket.id)
        if not queued:
            continue

        # Check no active jobs for this ticket
        active_job = db.execute(
            select(Job.id)
            .where(
                and_(
                    Job.ticket_id == ticket.id,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            )
            .limit(1)
        ).scalar_one_or_none()

        if active_job:
            # Put message back if there's already an active job
            queued_message_service.queue_message(ticket.id, queued.message)
            continue

        # Determine valid target state per state machine:
        # DONE → EXECUTING (the only valid exit from DONE)
        # NEEDS_HUMAN → EXECUTING (human resolved, back to executing)
        # BLOCKED → EXECUTING (retry execution)
        old_state = ticket.state
        old_state_enum = TicketState(old_state)
        target_state = {
            TicketState.DONE: TicketState.EXECUTING,
            TicketState.NEEDS_HUMAN: TicketState.EXECUTING,
            TicketState.BLOCKED: TicketState.EXECUTING,
        }.get(old_state_enum, TicketState.EXECUTING)

        ticket.state = target_state.value

        # Create event for the queued message execution
        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.TRANSITIONED.value,
            from_state=old_state,
            to_state=target_state.value,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason=f"Executing queued follow-up: {queued.message[:100]}...",
            payload_json=json.dumps(
                {
                    "action": "queued_followup",
                    "queued_message": queued.message,
                    "queued_at": queued.queued_at.isoformat(),
                }
            ),
        )
        db.add(event)

        # Store follow-up prompt in Redis for the worker to pick up
        # The executor will append this to the prompt bundle
        queued_message_service.set_followup_prompt(ticket.id, queued.message)

        # Create execute job
        job = Job(
            ticket_id=ticket.id,
            board_id=ticket.board_id,
            kind=JobKind.EXECUTE.value,
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        db.flush()
        db.refresh(job)

        logger.info(
            f"Executing queued message for ticket {ticket.id}: {queued.message[:50]}..."
        )
        return job.id

    return None


def _enqueue_celery_job_sync(job_id: str) -> None:
    """Enqueue a task for a job (synchronous).

    Uses unified task dispatch to support both SQLite and Celery backends.
    """
    from app.services.task_dispatch import enqueue_task

    try:
        with get_sync_db() as db:
            job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
            if not job:
                logger.error(f"Job {job_id} not found when enqueueing task")
                return

            # Skip if already has task ID
            if job.celery_task_id:
                logger.debug(f"Job {job_id} already has task {job.celery_task_id}")
                return

            # Enqueue via unified dispatch
            task = enqueue_task("execute_ticket", args=[job_id])
            job.celery_task_id = task.id
            db.commit()

            logger.info(f"Enqueued task {task.id} for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to enqueue task for job {job_id}: {e}")


def _handle_blocked_tickets_sync(db, config: PlannerConfig) -> int:
    """Handle blocked tickets and generate follow-ups (synchronous).

    Returns:
        Number of follow-ups created.
    """
    followups_created = 0

    # Find blocked tickets
    blocked_tickets = (
        db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.BLOCKED.value)
            .options(selectinload(Ticket.goal), selectinload(Ticket.events))
        )
        .scalars()
        .all()
    )

    llm_service = LLMService(config)

    for ticket in blocked_tickets:
        # Cap: max follow-ups per tick
        if followups_created >= config.max_followups_per_tick:
            break

        # Cap: count existing follow-ups
        existing_followup_count = sum(
            1
            for event in ticket.events
            if event.payload_json and FOLLOWUP_MARKER in event.payload_json
        )
        if existing_followup_count >= config.max_followups_per_ticket:
            continue

        # Get blocker reason and payload
        blocker_reason = None
        blocker_payload = {}
        for event in reversed(ticket.events):
            if event.to_state == TicketState.BLOCKED.value and event.reason:
                blocker_reason = event.reason
                if event.payload_json:
                    try:
                        blocker_payload = json.loads(event.payload_json)
                    except (json.JSONDecodeError, TypeError):
                        pass
                break

        # Skip: tickets with skip_followup flag
        if blocker_payload.get("skip_followup"):
            continue

        # Skip: tickets with manual work follow-up
        if blocker_payload.get("manual_work_followup_id"):
            continue

        # Skip certain blocker reasons
        if blocker_reason and _should_skip_followup(blocker_reason, config):
            continue

        # Fetch sibling ticket titles in the same goal to avoid duplicates
        sibling_titles: list[str] = []
        if ticket.goal_id:
            sibling_result = db.execute(
                select(Ticket.title).where(
                    and_(
                        Ticket.goal_id == ticket.goal_id,
                        Ticket.id != ticket.id,
                    )
                )
            )
            sibling_titles = [row[0] for row in sibling_result.fetchall()]

        # Generate follow-up proposal
        try:
            proposal = _generate_followup_proposal(
                ticket_title=ticket.title,
                ticket_description=ticket.description,
                blocker_reason=blocker_reason,
                goal_title=ticket.goal.title if ticket.goal else None,
                goal_description=ticket.goal.description if ticket.goal else None,
                llm_service=llm_service,
                config=config,
                existing_ticket_titles=sibling_titles,
            )
        except Exception as e:
            logger.error(f"Failed to generate follow-up for ticket {ticket.id}: {e}")
            continue

        # Create follow-up ticket
        followup_ticket = Ticket(
            goal_id=ticket.goal_id,
            title=proposal["title"],
            description=proposal["description"],
            state=TicketState.PROPOSED.value,
            priority=ticket.priority,
        )
        db.add(followup_ticket)
        db.flush()
        db.refresh(followup_ticket)

        # Create creation event
        creation_event = TicketEvent(
            ticket_id=followup_ticket.id,
            event_type=EventType.CREATED.value,
            from_state=None,
            to_state=TicketState.PROPOSED.value,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason=f"Follow-up for blocked ticket: {ticket.title}",
            payload_json=json.dumps(
                {
                    "parent_ticket_id": ticket.id,
                    "verification": proposal.get("verification", []),
                }
            ),
        )
        db.add(creation_event)

        # Create link event on blocked ticket
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
        db.add(link_event)

        followups_created += 1
        logger.info(
            f"Created follow-up ticket {followup_ticket.id} for blocked ticket {ticket.id}"
        )

        try:
            from app.services.orchestrator_log import add_orchestrator_log

            add_orchestrator_log(
                "INFO",
                f"Follow-up created: '{followup_ticket.title}'",
                {
                    "followup_ticket_id": followup_ticket.id,
                    "blocked_ticket_id": ticket.id,
                    "blocked_ticket_title": ticket.title,
                    "blocker_reason": blocker_reason,
                    "existing_siblings": len(sibling_titles),
                },
            )
        except Exception:
            pass

    return followups_created


def _should_skip_followup(blocker_reason: str, config: PlannerConfig) -> bool:
    """Check if this blocker reason should skip follow-up generation."""
    reason_lower = blocker_reason.lower()
    for skip_reason in config.skip_followup_reasons:
        if skip_reason.lower() in reason_lower:
            return True
    return False


def _generate_followup_proposal(
    ticket_title: str,
    ticket_description: str | None,
    blocker_reason: str | None,
    goal_title: str | None,
    goal_description: str | None,
    llm_service: LLMService,
    config: PlannerConfig,
    existing_ticket_titles: list[str] | None = None,
) -> dict:
    """Generate a follow-up ticket proposal using LLM."""
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

    context = "\n".join(context_parts)

    # Include existing tickets so LLM avoids duplicates
    existing_section = ""
    if existing_ticket_titles:
        ticket_list = "\n".join(f"- {t}" for t in existing_ticket_titles)
        existing_section = f"""

## Existing Tickets (DO NOT DUPLICATE)
These tickets already exist in the same goal. Do NOT create a follow-up that overlaps with any of these:
{ticket_list}"""

    system_prompt = """You are a technical project planner. Given a blocked ticket, propose a follow-up ticket that addresses the blocker.

Your response MUST be valid JSON with this exact structure:
{
  "title": "Short, actionable title for the follow-up ticket",
  "description": "Clear description of what needs to be done to unblock the original ticket",
  "verification": ["command1", "command2"]
}

Guidelines:
- Do NOT create a ticket that duplicates an existing one"""

    user_prompt = f"""A ticket is blocked and needs a follow-up ticket to address the blocker.

{context}{existing_section}

Generate a follow-up ticket proposal as JSON."""

    try:
        response = llm_service.call_completion(
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=config.max_tokens_followup,
            system_prompt=system_prompt,
        )
        data = llm_service.safe_parse_json(response.content, {})

        return {
            "title": data.get("title", "Follow-up for blocked ticket"),
            "description": data.get(
                "description", "Address the blocker from the original ticket."
            ),
            "verification": data.get("verification", []),
        }
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return {
            "title": f"Follow-up: {ticket_title}",
            "description": f"Address blocker: {blocker_reason or 'Unknown blocker'}",
            "verification": [],
        }


def _generate_reflections_sync(db, config: PlannerConfig) -> int:
    """Generate reflections for done tickets (synchronous).

    Returns:
        Number of reflections added.
    """
    reflections_added = 0

    # Find done tickets
    done_tickets = (
        db.execute(
            select(Ticket)
            .where(Ticket.state == TicketState.DONE.value)
            .options(selectinload(Ticket.events), selectinload(Ticket.evidence))
        )
        .scalars()
        .all()
    )

    llm_service = LLMService(config)

    for ticket in done_tickets:
        # Check if already has reflection
        has_reflection = any(
            event.payload_json and REFLECTION_MARKER in event.payload_json
            for event in ticket.events
        )

        if has_reflection:
            continue

        # Build summaries
        events_summary = _summarize_events(ticket.events)
        evidence_summary = _summarize_evidence(ticket.evidence)

        # Generate reflection
        try:
            reflection = _generate_reflection_summary(
                ticket_title=ticket.title,
                ticket_description=ticket.description,
                events_summary=events_summary,
                evidence_summary=evidence_summary,
                llm_service=llm_service,
                config=config,
            )
        except Exception as e:
            logger.error(f"Failed to generate reflection for ticket {ticket.id}: {e}")
            continue

        # Create reflection event
        reflection_event = TicketEvent(
            ticket_id=ticket.id,
            event_type=REFLECTION_EVENT_TYPE,
            from_state=ticket.state,
            to_state=ticket.state,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason=reflection,
            payload_json=json.dumps(
                {
                    REFLECTION_MARKER: True,
                    "type": "reflection_added",
                }
            ),
        )
        db.add(reflection_event)

        reflections_added += 1
        logger.info(f"Generated reflection for ticket {ticket.id}")

    return reflections_added


def _summarize_events(events) -> str:
    """Summarize ticket events."""
    if not events:
        return "No events"

    transitions = []
    for event in events:
        if event.event_type == EventType.TRANSITIONED.value:
            transitions.append(f"{event.from_state} → {event.to_state}")
        elif event.event_type == EventType.CREATED.value:
            transitions.append(f"created ({event.to_state})")

    if transitions:
        return " → ".join(transitions[:5])
    return "No state transitions"


def _summarize_evidence(evidence) -> str:
    """Summarize verification evidence."""
    if not evidence:
        return "No verification evidence"

    passed = sum(1 for e in evidence if e.exit_code == 0)
    failed = len(evidence) - passed

    parts = []
    if passed:
        parts.append(f"{passed} passed")
    if failed:
        parts.append(f"{failed} failed")

    return ", ".join(parts) if parts else "No evidence"


def _generate_reflection_summary(
    ticket_title: str,
    ticket_description: str | None,
    events_summary: str | None,
    evidence_summary: str | None,
    llm_service: LLMService,
    config: PlannerConfig,
) -> str:
    """Generate a reflection summary using LLM."""
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
}"""

    user_prompt = f"""A ticket has been completed. Generate a reflection summary.

{context}

Generate a reflection summary as JSON."""

    try:
        response = llm_service.call_completion(
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=config.max_tokens_reflection,
            system_prompt=system_prompt,
        )
        data = llm_service.safe_parse_json(response.content, {})

        return data.get("summary", f"Completed: {ticket_title}")
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        return f"Ticket '{ticket_title}' was completed successfully."
