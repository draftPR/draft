"""Service layer for Goal operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ResourceNotFoundError
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalUpdate
from app.schemas.planner import PlanGoalDraft, bucket_to_priority
from app.schemas.ticket import TicketCreate


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

    async def get_goals(self, board_id: str | None = None) -> list[Goal]:
        """
        Get all goals, optionally filtered by board.

        Args:
            board_id: If provided, only return goals for this board

        Returns:
            List of Goal instances
        """
        stmt = select(Goal)
        if board_id:
            stmt = stmt.where(Goal.board_id == board_id)
        result = await self.db.execute(stmt.order_by(Goal.created_at.desc()))
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

    async def create_from_plan(
        self, board_id: str, drafts: list[PlanGoalDraft]
    ) -> tuple[list[str], int, int]:
        """Create a draft plan's goals and PROPOSED tickets (caller commits).

        A draft with ``existing_goal_id`` adds its tickets to that goal, which
        must belong to ``board_id``. ``blocked_by`` resolves by title against
        tickets listed earlier in the same goal, so dependencies stay acyclic.

        Returns:
            (goal ids in plan order, goals created, tickets created)
        """
        from app.services.ticket_service import TicketService

        tickets = TicketService(self.db)
        goal_ids: list[str] = []
        goals_created = tickets_created = 0
        for draft in drafts:
            if draft.existing_goal_id:
                goal = await self.get_goal_by_id(draft.existing_goal_id)
                if goal.board_id != board_id:
                    raise ResourceNotFoundError("Goal", draft.existing_goal_id)
            else:
                goal = await self.create_goal(
                    GoalCreate(
                        title=draft.title,
                        description=draft.description or None,
                        board_id=board_id,
                    )
                )
                goals_created += 1
            created: dict[str, str] = {}  # lowercase title -> ticket id
            for t in draft.tickets:
                ticket = await tickets.create_ticket(
                    TicketCreate(
                        goal_id=goal.id,
                        title=t.title,
                        description=t.description or None,
                        priority=bucket_to_priority(t.priority_bucket),
                        blocked_by_ticket_id=created.get(
                            (t.blocked_by or "").strip().lower()
                        ),
                    )
                )
                created[t.title.strip().lower()] = ticket.id
            tickets_created += len(draft.tickets)
            goal_ids.append(goal.id)
        return goal_ids, goals_created, tickets_created
