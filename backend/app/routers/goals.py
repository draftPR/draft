"""API router for Goal endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.goal import (
    AutonomySettings,
    AutonomyStatusResponse,
    GoalCreate,
    GoalListResponse,
    GoalResponse,
    GoalUpdate,
)
from app.schemas.planner import (
    GenerateTicketsRequest,
    GenerateTicketsResponse,
    ReflectionResult,
)
from app.services.config_service import ConfigService
from app.services.goal_service import GoalService
from app.services.ticket_generation_service import TicketGenerationService
from app.services.udar_planner_service import UDARPlannerService
from app.utils.ignored_fields import add_ignored_fields_header, check_ignored_fields

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal",
)
async def create_goal(
    data: GoalCreate,
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Create a new goal."""
    service = GoalService(db)
    goal = await service.create_goal(data)
    return GoalResponse.model_validate(goal)


@router.get(
    "",
    response_model=GoalListResponse,
    summary="List all goals",
)
async def list_goals(
    db: AsyncSession = Depends(get_db),
) -> GoalListResponse:
    """Get all goals."""
    service = GoalService(db)
    goals = await service.get_goals()
    return GoalListResponse(
        goals=[GoalResponse.model_validate(g) for g in goals],
        total=len(goals),
    )


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Get a goal by ID",
)
async def get_goal(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Get a goal by its ID."""
    service = GoalService(db)
    goal = await service.get_goal_by_id(goal_id)
    return GoalResponse.model_validate(goal)


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Update a goal",
)
async def update_goal(
    goal_id: str,
    data: GoalUpdate,
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Update a goal with partial data. Supports updating autonomy settings."""
    service = GoalService(db)
    goal = await service.update_goal(goal_id, data)
    await db.commit()
    return GoalResponse.model_validate(goal)


@router.patch(
    "/{goal_id}/autonomy",
    response_model=GoalResponse,
    summary="Update autonomy settings for a goal",
)
async def update_autonomy(
    goal_id: str,
    data: AutonomySettings,
    db: AsyncSession = Depends(get_db),
) -> GoalResponse:
    """Update autonomy settings for a goal. Accepts partial updates."""
    service = GoalService(db)
    update_data = GoalUpdate(**data.model_dump())
    goal = await service.update_goal(goal_id, update_data)
    await db.commit()
    return GoalResponse.model_validate(goal)


@router.get(
    "/{goal_id}/autonomy/status",
    response_model=AutonomyStatusResponse,
    summary="Get autonomy status for a goal",
)
async def get_autonomy_status(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
) -> AutonomyStatusResponse:
    """Get autonomy status including settings, approval count, and budget info."""
    service = GoalService(db)
    goal = await service.get_goal_by_id(goal_id)

    # Check budget remaining
    budget_remaining = None
    if goal.budget:
        if goal.budget.total_budget is not None:
            # Would need cost tracking service for actual spend, placeholder for now
            budget_remaining = goal.budget.total_budget

    return AutonomyStatusResponse(
        goal_id=goal.id,
        autonomy_enabled=goal.autonomy_enabled,
        auto_approve_tickets=goal.auto_approve_tickets,
        auto_approve_revisions=goal.auto_approve_revisions,
        auto_merge=goal.auto_merge,
        auto_approve_followups=goal.auto_approve_followups,
        max_auto_approvals=goal.max_auto_approvals,
        auto_approval_count=goal.auto_approval_count,
        budget_remaining=budget_remaining,
    )


@router.get(
    "/{goal_id}/generate-tickets/stream",
    summary="Generate tickets with streaming progress (SSE)",
)
async def generate_tickets_stream(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate tickets with real-time streaming feedback using Server-Sent Events (SSE).

    The stream sends JSON events with the following types:
    - status: Progress updates like "Analyzing codebase...", "Generating tickets..."
    - agent_output: Real-time output from the agent CLI
    - ticket: Each ticket as it's created
    - complete: Final summary when done
    - error: If something goes wrong
    """
    import asyncio
    import json as json_lib
    import logging

    from fastapi.responses import StreamingResponse

    logger = logging.getLogger(__name__)

    async def event_generator():
        try:
            # Send initial status
            yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Starting ticket generation...'})}\n\n"
            await asyncio.sleep(0.05)

            # Load config for validate_tickets setting
            config_service = ConfigService()
            config = config_service.load_config()

            yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Analyzing goal and building prompt...'})}\n\n"
            await asyncio.sleep(0.05)

            service = TicketGenerationService(db)

            # Create a queue for streaming agent output
            output_queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def stream_callback(line: str):
                """Called from subprocess thread when agent outputs a line."""
                try:
                    loop.call_soon_threadsafe(
                        output_queue.put_nowait, ("agent_output", line)
                    )
                except Exception:
                    pass

            yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Starting agent CLI...'})}\n\n"
            await asyncio.sleep(0.05)

            # Start generation task - repo_root resolved inside service from goal's board
            generation_task = asyncio.create_task(
                service.generate_from_goal(
                    goal_id=goal_id,
                    include_readme=False,
                    validate_tickets=config.planner_config.features.validate_tickets,
                    stream_callback=stream_callback,
                )
            )

            # Stream agent output as it comes in
            while not generation_task.done():
                try:
                    msg_type, data = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                    if msg_type == "agent_output":
                        yield f"data: {json_lib.dumps({'type': 'agent_output', 'message': data})}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Get final result
            try:
                result = await generation_task
            except Exception as e:
                logger.error(f"Ticket generation failed: {e}", exc_info=True)
                yield f"data: {json_lib.dumps({'type': 'error', 'message': str(e)})}\n\n"
                return

            # Drain any remaining messages
            while not output_queue.empty():
                msg_type, data = await output_queue.get()
                if msg_type == "agent_output":
                    yield f"data: {json_lib.dumps({'type': 'agent_output', 'message': data})}\n\n"

            # Stream each created ticket
            if result.tickets:
                yield f"data: {json_lib.dumps({'type': 'status', 'message': f'Created {len(result.tickets)} ticket(s)'})}\n\n"
                for ticket in result.tickets:
                    yield f"data: {json_lib.dumps({'type': 'ticket', 'ticket': {'id': ticket.id, 'title': ticket.title, 'priority': ticket.priority}})}\n\n"
                    await asyncio.sleep(0.05)
            else:
                yield f"data: {json_lib.dumps({'type': 'error', 'message': 'No tickets generated. Check backend logs.'})}\n\n"

            # Send completion
            yield f"data: {json_lib.dumps({'type': 'complete', 'count': len(result.tickets)})}\n\n"

        except ValueError as e:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Ticket generation stream error: {e}", exc_info=True)
            yield f"data: {json_lib.dumps({'type': 'error', 'message': f'Generation failed: {str(e)}'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{goal_id}/generate-tickets",
    summary="Generate proposed tickets using LLM planner",
)
async def generate_tickets(
    goal_id: str,
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate proposed tickets for a goal using AI planner.

    The planner analyzes the goal and repository context to generate
    2-5 specific, actionable tickets with verification commands.

    **Security:** Repository path is inferred from server config (smartkanban.yaml),
    NOT from client request. The `workspace_path` field is deprecated and ignored.
    If sent, it will appear in X-Ignored-Fields response header.

    **New in v2:** Tickets now include priority buckets (P0-P3) which are
    normalized to numeric priorities (P0=90, P1=70, P2=50, P3=30).

    Requires LLM API key environment variables (OPENAI_API_KEY, etc.).
    """
    import json

    # Parse raw body to check for ignored fields
    body = await raw_request.body()
    try:
        raw_body = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raw_body = {}

    # Check for ignored/deprecated fields
    allowed_fields = {"include_readme"}
    ignored_fields = check_ignored_fields(raw_request, raw_body, allowed_fields)

    # Parse into Pydantic model
    request = GenerateTicketsRequest(**{k: v for k, v in raw_body.items() if k in allowed_fields})

    # Get repo root from config - DO NOT accept arbitrary paths from client
    config_service = ConfigService()
    config = config_service.load_config()
    repo_root = Path(config.project.repo_root).resolve()

    if not repo_root.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Configured repo_root does not exist: {repo_root}",
        )

    # Check if UDAR agent is enabled (Phase 2 feature flag)
    if config.planner_config.udar.enabled:
        # Use UDAR agent for adaptive ticket generation
        udar_service = UDARPlannerService(db)
        try:
            udar_result = await udar_service.generate_from_goal(goal_id=goal_id)
            # Convert UDAR result to expected format
            result_tickets = [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "description": t.get("description"),
                    "priority": t.get("priority", 50),
                    "state": "proposed",
                }
                for t in udar_result.get("tickets", [])
            ]
            result = type('obj', (object,), {'tickets': result_tickets})()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        # Use legacy ticket generation service
        service = TicketGenerationService(db)
        try:
            result = await service.generate_from_goal(
                goal_id=goal_id,
                repo_root=repo_root,
                include_readme=request.include_readme,
                validate_tickets=config.planner_config.features.validate_tickets,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # Build response
    if len(result.tickets) == 0:
        response_data = GenerateTicketsResponse(
            tickets=[],
            goal_id=goal_id,
        )
    else:
        response_data = GenerateTicketsResponse(
            tickets=result.tickets,
            goal_id=goal_id,
        )

    # Build response with X-Ignored-Fields header if applicable
    response = JSONResponse(content=response_data.model_dump())
    add_ignored_fields_header(response, ignored_fields)

    return response


@router.post(
    "/{goal_id}/reflect-on-tickets",
    response_model=ReflectionResult,
    summary="Reflect on proposed tickets for quality and coverage",
)
async def reflect_on_tickets(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReflectionResult:
    """
    Evaluate proposed tickets for a goal using AI reflection.

    This endpoint analyzes the PROPOSED tickets for a goal and returns:
    - **overall_quality**: "good", "needs_work", or "insufficient"
    - **quality_notes**: Detailed assessment of ticket quality
    - **coverage_gaps**: Areas not covered by current tickets
    - **suggested_changes**: Recommended priority adjustments

    **Important:** This endpoint does NOT apply changes. To apply suggested
    priority changes, use `POST /tickets/bulk-update-priority` with the
    suggested ticket IDs and new priority buckets.

    This allows humans to review suggestions before applying them.
    """
    service = TicketGenerationService(db)
    try:
        return await service.reflect_on_proposals(goal_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
