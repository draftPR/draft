"""API router for Goal endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.goal import GoalCreate, GoalListResponse, GoalResponse
from app.services.goal_service import GoalService

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
