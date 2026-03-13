"""API router for Planner endpoints."""

import logging
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.ticket_event import TicketEvent
from app.schemas.planner import (
    PlannerAction,
    PlannerStartRequest,
    PlannerStartResponse,
    PlannerTickRequest,
    PlannerTickResponse,
)
from app.services.config_service import ConfigService
from app.services.planner_service import PlannerLockError, PlannerService
from app.state_machine import ActorType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planner", tags=["planner"])


class PlannerFeaturesStatus(BaseModel):
    """Status of planner feature flags."""

    auto_execute: bool
    propose_followups: bool
    generate_reflections: bool


class LastTickStats(BaseModel):
    """Statistics from the most recent planner tick."""

    executed: int
    followups_created: int
    reflections_added: int
    last_tick_at: datetime | None


class LLMHealthCheck(BaseModel):
    """Result of LLM health check."""

    healthy: bool
    latency_ms: int | None = None
    error: str | None = None


class PlannerStatusResponse(BaseModel):
    """Response containing planner configuration status."""

    model: str
    llm_configured: bool
    llm_provider: str | None
    llm_health: LLMHealthCheck | None = None  # Only populated when health_check=true
    features: PlannerFeaturesStatus
    max_followups_per_ticket: int
    max_followups_per_tick: int
    last_tick: LastTickStats | None


def _detect_llm_provider(model: str | None = None) -> tuple[bool, str | None]:
    """Detect if an LLM is configured and which provider.

    Supports both API-key-based providers and CLI-based agents (e.g. claude, cursor).

    Returns:
        Tuple of (is_configured, provider_name)
    """
    import shutil

    # CLI-based models (no API key needed — CLI handles auth)
    # Model format: "cli/claude", "cli/cursor", etc.
    if model and model.startswith("cli/"):
        cli_name = model.split("/", 1)[1]  # e.g. "claude", "cursor"
        if shutil.which(cli_name):
            return True, f"cli:{cli_name}"
        # CLI binary not found on PATH
        return False, f"cli:{cli_name} (not found)"

    # Check for common API keys
    if os.environ.get("OPENAI_API_KEY"):
        return True, "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True, "anthropic"
    if os.environ.get("AZURE_API_KEY"):
        return True, "azure"
    if os.environ.get("COHERE_API_KEY"):
        return True, "cohere"
    # Check for AWS Bedrock credentials
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True, "aws-bedrock"
    # LiteLLM also supports LITELLM_API_KEY for some providers
    if os.environ.get("LITELLM_API_KEY"):
        return True, "litellm"
    return False, None


async def _check_llm_health(model: str) -> LLMHealthCheck:
    """Perform a minimal health check on the LLM.

    Makes a tiny request to verify the LLM is accessible.
    Uses max_tokens=1 to minimize cost.

    Args:
        model: The model identifier to test.

    Returns:
        LLMHealthCheck with status, latency, and any error.
    """
    import time

    try:
        from litellm import acompletion

        start_time = time.time()

        # Minimal request to test connectivity
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
            timeout=10,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Check if we got a valid response
        if response and response.choices:
            return LLMHealthCheck(healthy=True, latency_ms=latency_ms)
        else:
            return LLMHealthCheck(
                healthy=False,
                latency_ms=latency_ms,
                error="Empty response from LLM",
            )

    except Exception as e:
        error_msg = str(e)
        # Truncate very long error messages
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        logger.warning(f"LLM health check failed: {error_msg}")
        return LLMHealthCheck(healthy=False, error=error_msg)


async def _get_last_tick_stats(db: AsyncSession) -> LastTickStats | None:
    """Query last tick stats from recent planner events.

    Looks at planner events from the last hour to find the most recent tick
    and count actions by type.

    OPTIMIZATION NOTE: This queries all planner events in the last hour
    and computes counts in Python. For high-volume usage, consider:
    - Store a single planner_tick_summary event per tick with counts in payload_json
    - Then this function reads one row instead of scanning many
    Not needed for MVP, but keep in mind for scale.
    """
    # Find planner events from the last hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)

    result = await db.execute(
        select(TicketEvent)
        .options(selectinload(TicketEvent.ticket))
        .where(
            and_(
                TicketEvent.actor_type == ActorType.PLANNER.value,
                TicketEvent.actor_id == "planner",
                TicketEvent.created_at >= one_hour_ago,
            )
        )
        .order_by(TicketEvent.created_at.desc())
    )
    events = list(result.scalars().all())

    if not events:
        return None

    # Find the most recent tick boundary (events within 5 seconds of the newest)
    newest_time = events[0].created_at
    tick_window = timedelta(seconds=5)

    tick_events = [e for e in events if (newest_time - e.created_at) < tick_window]

    # Count by type based on payload markers
    executed = 0
    followups_created = 0
    reflections_added = 0

    for event in tick_events:
        payload = event.get_payload() or {}

        if payload.get("action") == "enqueued_execute":
            executed += 1
        elif payload.get("planner_followup_created"):
            followups_created += 1
        elif payload.get("planner_reflection"):
            reflections_added += 1

    return LastTickStats(
        executed=executed,
        followups_created=followups_created,
        reflections_added=reflections_added,
        last_tick_at=newest_time,
    )


@router.get(
    "/status",
    response_model=PlannerStatusResponse,
    summary="Get planner configuration status",
)
async def get_planner_status(
    db: AsyncSession = Depends(get_db),
    health_check: bool = Query(
        default=False,
        description="If true, performs a live health check on the LLM (makes a minimal API call)",
    ),
) -> PlannerStatusResponse:
    """
    Get the current planner configuration status.

    Returns information about:
    - Which LLM model is configured
    - Whether an LLM API key is present
    - Which features are enabled
    - Safety caps for follow-ups
    - Stats from the last tick (executed, follow-ups, reflections)

    **Optional Health Check:**
    Pass `?health_check=true` to verify the LLM is actually accessible.
    This makes a minimal API call (max_tokens=1) to test connectivity.
    Note: This incurs a small cost and adds latency.

    This helps debug "why didn't follow-ups happen?" issues.
    """
    config_service = ConfigService()
    # Load fresh config without cache (in case draft.yaml was edited)
    config = config_service.load_config(use_cache=False).planner_config

    llm_configured, llm_provider = _detect_llm_provider(model=config.model)

    # Get last tick stats
    last_tick = await _get_last_tick_stats(db)

    # Optionally perform LLM health check
    llm_health = None
    if health_check and llm_configured:
        llm_health = await _check_llm_health(config.model)

    return PlannerStatusResponse(
        model=config.model,
        llm_configured=llm_configured,
        llm_provider=llm_provider,
        llm_health=llm_health,
        features=PlannerFeaturesStatus(
            auto_execute=config.features.auto_execute,
            propose_followups=config.features.propose_followups,
            generate_reflections=config.features.generate_reflections,
        ),
        max_followups_per_ticket=config.max_followups_per_ticket,
        max_followups_per_tick=config.max_followups_per_tick,
        last_tick=last_tick,
    )


@router.post(
    "/tick",
    response_model=PlannerTickResponse,
    summary="Run one planner decision cycle (debug/manual)",
)
async def planner_tick(
    request: PlannerTickRequest = PlannerTickRequest(),
    db: AsyncSession = Depends(get_db),
) -> PlannerTickResponse:
    """
    Run one decision cycle of the planner (single tick for debugging).

    **For normal operation, use `/planner/start` instead.**

    This endpoint runs a single decision cycle and returns immediately.
    Use it for debugging or manual control.

    The planner evaluates the current board state and takes actions:

    1. **Queue tickets** (deterministic): If no ticket is executing OR verifying,
       queues ALL planned tickets ordered by priority.

    2. **Handle blocked tickets** (LLM-powered): For BLOCKED tickets without
       follow-ups, generates and creates follow-up ticket proposals.

    3. **Generate reflections** (LLM-powered): For DONE tickets without
       reflections, generates summary comments as TicketEvents.

    **Concurrency Safety:**
    - Only one tick can run at a time (uses database lock)
    - Returns 409 Conflict if another tick is already in progress

    Returns a summary of actions taken during this tick.
    """
    service = PlannerService(db)
    try:
        return await service.tick()
    except PlannerLockError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )


@router.post(
    "/start",
    response_model=PlannerStartResponse,
    summary="Start autopilot - run until queue is empty",
)
async def planner_start(
    request: PlannerStartRequest = PlannerStartRequest(),
    db: AsyncSession = Depends(get_db),
) -> PlannerStartResponse:
    """
    Start the autopilot and run until all planned tickets are processed.

    This is the main entry point for automated ticket processing:

    1. **Queues all planned tickets** ordered by priority
    2. **Polls for completion** - waits for each ticket to finish
    3. **Continues until queue is empty** or max duration reached
    4. **Returns summary** of all actions taken

    **Flow:**
    - Queues all PLANNED tickets as execute jobs
    - Tickets transition: PLANNED → EXECUTING → VERIFYING → DONE/BLOCKED
    - Polls every `poll_interval_seconds` to check status
    - Stops when no more PLANNED/EXECUTING/VERIFYING tickets exist

    **Timeouts:**
    - Default max duration: 1 hour
    - Each individual job has its own timeout (from config)

    **Use `/tickets/{id}/execute` to run a single specific ticket.**
    """
    import asyncio
    import time

    from app.database import async_session_maker
    from app.models.job import Job, JobKind, JobStatus
    from app.models.ticket import Ticket
    from app.state_machine import TicketState

    start_time = time.time()
    all_actions: list[PlannerAction] = []
    tickets_completed = 0
    tickets_failed = 0

    # Initial tick to queue all planned tickets
    # force_execute=True ensures tickets are queued even if auto_execute is disabled in config
    # This allows users to keep auto_execute=false but still manually trigger autopilot
    service = PlannerService(db)
    try:
        initial_result = await service.tick(force_execute=True)
        all_actions.extend(initial_result.actions)
    except PlannerLockError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )

    # Count initially queued tickets
    tickets_queued = sum(
        1 for a in initial_result.actions if a.action_type == "enqueued_execute"
    )

    if tickets_queued == 0:
        return PlannerStartResponse(
            status="completed",
            message="No planned tickets to process",
            tickets_queued=0,
            tickets_completed=0,
            tickets_failed=0,
            total_actions=all_actions,
        )

    # Poll loop - wait for all tickets to complete
    # IMPORTANT: We release the DB connection between polls to avoid holding it for hours
    while True:
        elapsed = time.time() - start_time
        if elapsed >= request.max_duration_seconds:
            return PlannerStartResponse(
                status="timeout",
                message=f"Max duration of {request.max_duration_seconds}s reached",
                tickets_queued=tickets_queued,
                tickets_completed=tickets_completed,
                tickets_failed=tickets_failed,
                total_actions=all_actions,
            )

        # Use a fresh session for each poll to avoid holding connections
        async with async_session_maker() as poll_db:
            # Check current state
            # Count active tickets (executing or verifying)
            active_result = await poll_db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.state.in_(
                        [
                            TicketState.EXECUTING.value,
                            TicketState.VERIFYING.value,
                        ]
                    )
                )
            )
            active_count = active_result.scalar() or 0

            # Count planned tickets (still waiting)
            planned_result = await poll_db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.state == TicketState.PLANNED.value
                )
            )
            planned_count = planned_result.scalar() or 0

            # Count queued/running jobs
            jobs_result = await poll_db.execute(
                select(func.count(Job.id)).where(
                    and_(
                        Job.kind == JobKind.EXECUTE.value,
                        Job.status.in_(
                            [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
                        ),
                    )
                )
            )
            jobs_pending = jobs_result.scalar() or 0

            # Count completed and failed since start
            done_result = await poll_db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.state == TicketState.DONE.value
                )
            )
            tickets_completed = done_result.scalar() or 0

            blocked_result = await poll_db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.state == TicketState.BLOCKED.value
                )
            )
            tickets_failed = blocked_result.scalar() or 0

        logger.debug(
            f"Autopilot poll: active={active_count}, planned={planned_count}, "
            f"jobs_pending={jobs_pending}, done={tickets_completed}, blocked={tickets_failed}"
        )

        # If nothing is active and nothing planned, we're done
        if active_count == 0 and planned_count == 0 and jobs_pending == 0:
            # Run one more tick to handle any reflections/followups
            async with async_session_maker() as final_db:
                try:
                    final_service = PlannerService(final_db)
                    final_result = await final_service.tick()
                    all_actions.extend(final_result.actions)
                except PlannerLockError:
                    pass  # Ignore lock errors on final tick

            return PlannerStartResponse(
                status="completed",
                message=f"All {tickets_queued} ticket(s) processed",
                tickets_queued=tickets_queued,
                tickets_completed=tickets_completed,
                tickets_failed=tickets_failed,
                total_actions=all_actions,
            )

        # If there are still planned tickets but nothing active, run another tick
        if active_count == 0 and jobs_pending == 0 and planned_count > 0:
            async with async_session_maker() as tick_db:
                try:
                    tick_service = PlannerService(tick_db)
                    tick_result = await tick_service.tick()
                    all_actions.extend(tick_result.actions)
                except PlannerLockError:
                    pass  # Ignore, another tick is running

        # Wait before next poll
        await asyncio.sleep(request.poll_interval_seconds)


class ReleaseLockResponse(BaseModel):
    """Response from planner lock release."""

    released: bool
    message: str


@router.post(
    "/release-lock",
    response_model=ReleaseLockResponse,
    summary="Force-release the planner lock (emergency admin action)",
)
async def release_planner_lock(
    db: AsyncSession = Depends(get_db),
) -> ReleaseLockResponse:
    """
    Force-release the planner lock.

    **WARNING:** This is an emergency admin action for when the planner gets stuck.
    Only use this if the planner tick is hung and no tick is actually running.

    Deletes the planner_tick lock row from the planner_locks table.
    """
    from sqlalchemy import delete as sql_delete

    from app.models.planner_lock import PlannerLock

    result = await db.execute(
        sql_delete(PlannerLock).where(PlannerLock.lock_key == "planner_tick")
    )
    await db.commit()

    if result.rowcount > 0:
        logger.warning("Planner lock force-released by admin action")
        return ReleaseLockResponse(
            released=True,
            message="Planner lock released successfully",
        )
    else:
        return ReleaseLockResponse(
            released=False,
            message="No planner lock was held",
        )
