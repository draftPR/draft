"""API router for Goal endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import PaginatedResponse
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
    summary="List all goals",
)
async def list_goals(
    board_id: str | None = None,
    page: int | None = Query(
        None, ge=1, description="Page number (1-based). Omit for all results."
    ),
    limit: int | None = Query(
        None, ge=1, le=200, description="Items per page. Omit for all results."
    ),
    db: AsyncSession = Depends(get_db),
) -> GoalListResponse | PaginatedResponse[GoalResponse]:
    """Get all goals, optionally filtered by board_id.

    **Pagination (optional):**
    - If `page` and `limit` are provided, returns paginated response.
    - If omitted, returns all goals (backward compatible).
    """
    service = GoalService(db)
    goals = await service.get_goals(board_id=board_id)
    all_responses = [GoalResponse.model_validate(g) for g in goals]

    # If pagination params are provided, return paginated response
    if page is not None and limit is not None:
        total = len(all_responses)
        offset = (page - 1) * limit
        page_items = all_responses[offset : offset + limit]
        return PaginatedResponse[GoalResponse](
            items=page_items,
            total=total,
            page=page,
            limit=limit,
        )

    # Backward compatible: return all
    return GoalListResponse(
        goals=all_responses,
        total=len(all_responses),
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


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a goal and all its tickets",
)
async def delete_goal(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a goal and cascade delete all associated tickets, jobs, evidence, etc."""
    from sqlalchemy import delete as sql_delete

    from app.models.goal import Goal

    service = GoalService(db)
    await service.get_goal_by_id(goal_id)  # Verify exists
    await db.execute(sql_delete(Goal).where(Goal.id == goal_id))
    await db.commit()


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

    # Check budget remaining using CostTrackingService
    budget_remaining = None
    if goal.budget:
        if goal.budget.total_budget is not None:
            from app.services.cost_tracking_service import CostTrackingService

            cost_service = CostTrackingService(db)
            spent = await cost_service.get_goal_cost(goal_id)
            budget_remaining = max(0.0, goal.budget.total_budget - spent)

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
    "/{goal_id}/progress",
    summary="Get goal progress summary",
)
async def get_goal_progress(
    goal_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a summary of progress on a goal: ticket state breakdown,
    completion percentage, and whether the goal is blocked."""
    from app.services.delivery_pipeline import get_pipeline_status

    # Verify goal exists
    service = GoalService(db)
    await service.get_goal_by_id(goal_id)

    result = await get_pipeline_status(db, goal_id)
    result["goal_id"] = goal_id
    return result


@router.get(
    "/{goal_id}/generate-tickets/stream",
    summary="Generate tickets with streaming progress (SSE)",
)
async def generate_tickets_stream(
    goal_id: str,
):
    """
    Generate tickets with real-time streaming feedback using Server-Sent Events (SSE).

    Uses its own DB session to survive client disconnects (EventSource reconnects).

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

    from app.database import async_session_maker

    logger = logging.getLogger(__name__)

    async def event_generator():
        try:
            from app.services.cursor_log_normalizer import CursorLogNormalizer

            # Send initial status
            yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Starting ticket generation...'})}\n\n"
            await asyncio.sleep(0.05)

            # Use our own DB session (not request-scoped) so it survives SSE disconnects
            async with async_session_maker() as db:
                # Load config from goal's board (DB is source of truth)
                from sqlalchemy import select as sa_select

                from app.models.board import Board
                from app.models.goal import Goal
                from app.services.config_service import DraftConfig

                yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Loading goal and board configuration...'})}\n\n"

                goal_result = await db.execute(
                    sa_select(Goal).where(Goal.id == goal_id)
                )
                goal_obj = goal_result.scalar_one_or_none()
                if not goal_obj:
                    yield f"data: {json_lib.dumps({'type': 'error', 'message': f'Goal not found: {goal_id}'})}\n\n"
                    return

                board_config_dict = None
                if goal_obj and goal_obj.board_id:
                    board_result = await db.execute(
                        sa_select(Board).where(Board.id == goal_obj.board_id)
                    )
                    board_obj = board_result.scalar_one_or_none()
                    if board_obj and board_obj.config:
                        board_config_dict = board_obj.config

                config = DraftConfig.from_board_config(board_config_dict)

                yield f"data: {json_lib.dumps({'type': 'status', 'message': f'Using model: {config.planner_config.model}'})}\n\n"

                service = TicketGenerationService(db, config=config.planner_config)

                # Create a queue for streaming agent output
                output_queue: asyncio.Queue = asyncio.Queue()
                loop = asyncio.get_running_loop()

                # Normalizer to parse CLI JSON output into structured entries
                normalizer = CursorLogNormalizer()

                def stream_callback(line: str):
                    """Called from subprocess thread when agent outputs a line."""
                    try:
                        loop.call_soon_threadsafe(
                            output_queue.put_nowait, ("agent_output", line)
                        )
                    except Exception:
                        pass

                yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Launching agent subprocess...'})}\n\n"

                # Start generation task
                generation_task = asyncio.create_task(
                    service.generate_from_goal(
                        goal_id=goal_id,
                        include_readme=False,
                        validate_tickets=config.planner_config.features.validate_tickets,
                        stream_callback=stream_callback,
                    )
                )

                def _normalize_and_yield(line: str):
                    """Parse a raw CLI line into normalized entries."""
                    entries = normalizer.process_line(line)
                    results = []
                    for entry in entries:
                        entry_data = {
                            "entry_type": entry.entry_type.value,
                            "content": entry.content,
                            "sequence": entry.sequence,
                            "tool_name": entry.tool_name,
                            "action_type": entry.action_type.value
                            if entry.action_type
                            else None,
                            "tool_status": entry.tool_status.value
                            if entry.tool_status
                            else None,
                            "metadata": entry.metadata or {},
                            "timestamp": None,
                        }
                        results.append(
                            f"data: {json_lib.dumps({'type': 'agent_normalized', 'entry': entry_data})}\n\n"
                        )
                    return results

                # Stream agent output as it comes in
                while not generation_task.done():
                    try:
                        msg_type, data = await asyncio.wait_for(
                            output_queue.get(), timeout=0.1
                        )
                        if msg_type == "agent_output":
                            normalized_chunks = _normalize_and_yield(data)
                            if normalized_chunks:
                                for chunk in normalized_chunks:
                                    yield chunk
                            else:
                                yield f"data: {json_lib.dumps({'type': 'agent_output', 'message': data})}\n\n"
                    except TimeoutError:
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
                        normalized_chunks = _normalize_and_yield(data)
                        if normalized_chunks:
                            for chunk in normalized_chunks:
                                yield chunk
                        else:
                            yield f"data: {json_lib.dumps({'type': 'agent_output', 'message': data})}\n\n"

                # Flush any remaining buffered entries from normalizer
                for entry in normalizer.finalize():
                    entry_data = {
                        "entry_type": entry.entry_type.value,
                        "content": entry.content,
                        "sequence": entry.sequence,
                        "tool_name": entry.tool_name,
                        "action_type": entry.action_type.value
                        if entry.action_type
                        else None,
                        "tool_status": entry.tool_status.value
                        if entry.tool_status
                        else None,
                        "metadata": entry.metadata or {},
                        "timestamp": None,
                    }
                    yield f"data: {json_lib.dumps({'type': 'agent_normalized', 'entry': entry_data})}\n\n"

                # Stream each created ticket
                if result.tickets:
                    yield f"data: {json_lib.dumps({'type': 'status', 'message': f'Created {len(result.tickets)} ticket(s)'})}\n\n"
                    for ticket in result.tickets:
                        desc = ticket.description or ""
                        desc_short = desc[:150] + "..." if len(desc) > 150 else desc
                        ticket_data = {
                            "id": ticket.id,
                            "title": ticket.title,
                            "priority": ticket.priority,
                            "description": desc_short,
                            "blocked_by_title": getattr(
                                ticket, "blocked_by_title", None
                            ),
                        }
                        yield f"data: {json_lib.dumps({'type': 'ticket', 'ticket': ticket_data})}\n\n"
                        await asyncio.sleep(0.05)
                else:
                    yield f"data: {json_lib.dumps({'type': 'status', 'message': 'Agent finished but generated no tickets.'})}\n\n"

                # Send completion (always — even for 0 tickets so frontend gets onComplete)
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

    **Security:** Repository path is inferred from server config (draft.yaml),
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
    request = GenerateTicketsRequest(
        **{k: v for k, v in raw_body.items() if k in allowed_fields}
    )

    # Get config from goal's board (DB is source of truth)
    from sqlalchemy import select as sa_select

    from app.models.board import Board
    from app.models.goal import Goal
    from app.services.config_service import DraftConfig

    goal_result = await db.execute(sa_select(Goal).where(Goal.id == goal_id))
    goal_obj = goal_result.scalar_one_or_none()
    if not goal_obj:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")

    board_config_dict = None
    repo_root = None
    if goal_obj.board_id:
        board_result = await db.execute(
            sa_select(Board).where(Board.id == goal_obj.board_id)
        )
        board_obj = board_result.scalar_one_or_none()
        if board_obj:
            if board_obj.config:
                board_config_dict = board_obj.config
            repo_root = Path(board_obj.repo_root).resolve()

    config = DraftConfig.from_board_config(board_config_dict)

    if not repo_root or not repo_root.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Board repo_root does not exist: {repo_root}",
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
            result = type("obj", (object,), {"tickets": result_tickets})()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        # Use ticket generation service with board config
        service = TicketGenerationService(db, config=config.planner_config)
        try:
            result = await service.generate_from_goal(
                goal_id=goal_id,
                repo_root=repo_root,
                include_readme=request.include_readme,
                validate_tickets=config.planner_config.features.validate_tickets,
            )
        except ValueError as e:
            error_msg = str(e)
            if (
                "API key" in error_msg
                or "credentials" in error_msg
                or "unavailable" in error_msg
            ):
                raise HTTPException(status_code=503, detail=error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

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
