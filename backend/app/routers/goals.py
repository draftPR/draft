"""API router for Goal endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.goal import GoalCreate, GoalListResponse, GoalResponse
from app.schemas.planner import (
    GenerateTicketsRequest,
    GenerateTicketsResponse,
    ReflectionResult,
)
from app.services.config_service import ConfigService
from app.services.goal_service import GoalService
from app.services.ticket_generation_service import TicketGenerationService
from app.utils.ignored_fields import check_ignored_fields, add_ignored_fields_header

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

    service = TicketGenerationService(db)
    try:
        result = await service.generate_from_goal(
            goal_id=goal_id,
            repo_root=repo_root,
            include_readme=request.include_readme,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

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
