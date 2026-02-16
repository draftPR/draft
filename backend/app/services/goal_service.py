"""Service layer for Goal operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ResourceNotFoundError
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalUpdate


class GoalService:
    """Service class for Goal business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_goal(self, data: GoalCreate) -> Goal:
        """
        Create a new goal.

        Args:
            data: Goal creation data

        Returns:
            The created Goal instance
        """
        # If board_id provided, verify the board exists
        if data.board_id:
            from app.models.board import Board
            
            result = await self.db.execute(
                select(Board).where(Board.id == data.board_id)
            )
            if not result.scalar_one_or_none():
                raise ValueError(f"Board not found: {data.board_id}")
        
        goal = Goal(
            title=data.title,
            description=data.description,
            board_id=data.board_id,
            autonomy_enabled=data.autonomy_enabled,
            auto_approve_tickets=data.auto_approve_tickets,
            auto_approve_revisions=data.auto_approve_revisions,
            auto_merge=data.auto_merge,
            auto_approve_followups=data.auto_approve_followups,
            max_auto_approvals=data.max_auto_approvals,
        )
        self.db.add(goal)
        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def get_goals(self) -> list[Goal]:
        """
        Get all goals.

        Returns:
            List of all Goal instances
        """
        result = await self.db.execute(select(Goal).order_by(Goal.created_at.desc()))
        return list(result.scalars().all())

    async def update_goal(self, goal_id: str, data: GoalUpdate) -> Goal:
        """Update a goal with partial data.

        Args:
            goal_id: The UUID of the goal
            data: Fields to update (None fields are skipped)

        Returns:
            The updated Goal instance

        Raises:
            ResourceNotFoundError: If the goal is not found
        """
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            raise ResourceNotFoundError("Goal", goal_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(goal, field, value)

        await self.db.flush()
        await self.db.refresh(goal)
        return goal

    async def get_goal_by_id(self, goal_id: str) -> Goal:
        """
        Get a goal by its ID.

        Args:
            goal_id: The UUID of the goal

        Returns:
            The Goal instance

        Raises:
            ResourceNotFoundError: If the goal is not found
        """
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            raise ResourceNotFoundError("Goal", goal_id)
        return goal
