"""Cost tracking service for AI agent usage.

Tracks and aggregates costs across:
- Individual tickets
- Goals/sprints
- Time periods (daily, weekly, monthly)

Helps individual developers stay within budget and understand spending patterns.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_session import AgentSession
from app.models.ticket import Ticket
from app.services.agent_registry import AGENT_REGISTRY, AgentType

logger = logging.getLogger(__name__)


@dataclass
class CostSummary:
    """Cost summary for a period or entity."""
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    session_count: int
    avg_cost_per_session: float
    cost_by_agent: dict[str, float]
    cost_by_goal: dict[str, float]
    daily_costs: list[tuple[str, float]]  # (date, cost) pairs


@dataclass
class BudgetStatus:
    """Budget tracking status."""
    daily_budget: float | None
    daily_spent: float
    daily_remaining: float
    weekly_budget: float | None
    weekly_spent: float
    weekly_remaining: float
    monthly_budget: float | None
    monthly_spent: float
    monthly_remaining: float
    is_over_budget: bool
    warning_threshold_reached: bool  # 80% of any budget


class CostTrackingService:
    """Service for tracking and analyzing AI agent costs."""

    # Default budgets (can be overridden in config)
    DEFAULT_DAILY_BUDGET = 10.0  # $10/day
    DEFAULT_WEEKLY_BUDGET = 50.0  # $50/week
    DEFAULT_MONTHLY_BUDGET = 150.0  # $150/month
    WARNING_THRESHOLD = 0.8  # Warn at 80%

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_cost(
        self,
        agent_type: AgentType,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate cost for given token usage."""
        config = AGENT_REGISTRY.get(agent_type)
        if not config or not config.cost_per_1k_input:
            return 0.0

        input_cost = (input_tokens / 1000) * config.cost_per_1k_input
        output_cost = (output_tokens / 1000) * (config.cost_per_1k_output or config.cost_per_1k_input)

        return round(input_cost + output_cost, 6)

    async def get_period_cost(
        self,
        start_date: datetime,
        end_date: datetime,
        goal_id: str | None = None
    ) -> float:
        """Get total cost for a time period, optionally filtered by goal."""
        query = select(func.sum(AgentSession.estimated_cost_usd)).where(
            AgentSession.created_at >= start_date,
            AgentSession.created_at < end_date
        )

        if goal_id:
            query = query.join(Ticket).where(Ticket.goal_id == goal_id)

        result = await self.db.execute(query)
        total = result.scalar()
        return float(total or 0)

    async def get_daily_cost(self, date: datetime | None = None) -> float:
        """Get cost for a specific day (defaults to today)."""
        if date is None:
            date = datetime.utcnow()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        return await self.get_period_cost(start, end)

    async def get_weekly_cost(self, date: datetime | None = None) -> float:
        """Get cost for the week containing the given date."""
        if date is None:
            date = datetime.utcnow()

        # Start of week (Monday)
        start = date - timedelta(days=date.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(weeks=1)

        return await self.get_period_cost(start, end)

    async def get_monthly_cost(self, date: datetime | None = None) -> float:
        """Get cost for the month containing the given date."""
        if date is None:
            date = datetime.utcnow()

        start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)

        return await self.get_period_cost(start, end)

    async def get_budget_status(
        self,
        daily_budget: float | None = None,
        weekly_budget: float | None = None,
        monthly_budget: float | None = None
    ) -> BudgetStatus:
        """Get current budget status across all time periods."""
        daily_budget = daily_budget or self.DEFAULT_DAILY_BUDGET
        weekly_budget = weekly_budget or self.DEFAULT_WEEKLY_BUDGET
        monthly_budget = monthly_budget or self.DEFAULT_MONTHLY_BUDGET

        daily_spent = await self.get_daily_cost()
        weekly_spent = await self.get_weekly_cost()
        monthly_spent = await self.get_monthly_cost()

        daily_remaining = max(0, daily_budget - daily_spent)
        weekly_remaining = max(0, weekly_budget - weekly_spent)
        monthly_remaining = max(0, monthly_budget - monthly_spent)

        is_over_budget = (
            daily_spent > daily_budget or
            weekly_spent > weekly_budget or
            monthly_spent > monthly_budget
        )

        warning_reached = (
            daily_spent >= daily_budget * self.WARNING_THRESHOLD or
            weekly_spent >= weekly_budget * self.WARNING_THRESHOLD or
            monthly_spent >= monthly_budget * self.WARNING_THRESHOLD
        )

        return BudgetStatus(
            daily_budget=daily_budget,
            daily_spent=round(daily_spent, 2),
            daily_remaining=round(daily_remaining, 2),
            weekly_budget=weekly_budget,
            weekly_spent=round(weekly_spent, 2),
            weekly_remaining=round(weekly_remaining, 2),
            monthly_budget=monthly_budget,
            monthly_spent=round(monthly_spent, 2),
            monthly_remaining=round(monthly_remaining, 2),
            is_over_budget=is_over_budget,
            warning_threshold_reached=warning_reached
        )

    async def get_cost_summary(
        self,
        days: int = 30,
        goal_id: str | None = None
    ) -> CostSummary:
        """Get detailed cost summary for the last N days."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Base query
        base_query = select(AgentSession).where(
            AgentSession.created_at >= start_date,
            AgentSession.created_at < end_date
        )

        if goal_id:
            base_query = base_query.join(Ticket).where(Ticket.goal_id == goal_id)

        result = await self.db.execute(base_query)
        sessions = result.scalars().all()

        # Aggregate data
        total_cost = sum(s.estimated_cost_usd for s in sessions)
        total_input = sum(s.total_input_tokens for s in sessions)
        total_output = sum(s.total_output_tokens for s in sessions)
        session_count = len(sessions)

        # Cost by agent
        cost_by_agent: dict[str, float] = {}
        for session in sessions:
            agent = session.agent_type
            cost_by_agent[agent] = cost_by_agent.get(agent, 0) + session.estimated_cost_usd

        # Cost by goal (need to join with tickets)
        cost_by_goal: dict[str, float] = {}
        for session in sessions:
            if session.ticket and session.ticket.goal_id:
                goal_id = str(session.ticket.goal_id)
                cost_by_goal[goal_id] = cost_by_goal.get(goal_id, 0) + session.estimated_cost_usd

        # Daily breakdown
        daily_costs: dict[str, float] = {}
        for session in sessions:
            day_key = session.created_at.strftime("%Y-%m-%d")
            daily_costs[day_key] = daily_costs.get(day_key, 0) + session.estimated_cost_usd

        daily_list = sorted(daily_costs.items())

        return CostSummary(
            total_cost_usd=round(total_cost, 2),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            session_count=session_count,
            avg_cost_per_session=round(total_cost / max(1, session_count), 4),
            cost_by_agent={k: round(v, 2) for k, v in cost_by_agent.items()},
            cost_by_goal={k: round(v, 2) for k, v in cost_by_goal.items()},
            daily_costs=[(d, round(c, 2)) for d, c in daily_list]
        )

    async def get_ticket_cost(self, ticket_id: str) -> float:
        """Get total cost for a specific ticket."""
        query = select(func.sum(AgentSession.estimated_cost_usd)).where(
            AgentSession.ticket_id == ticket_id
        )
        result = await self.db.execute(query)
        total = result.scalar()
        return float(total or 0)

    async def get_goal_cost(self, goal_id: str) -> float:
        """Get total cost for all tickets in a goal."""
        query = (
            select(func.sum(AgentSession.estimated_cost_usd))
            .join(Ticket)
            .where(Ticket.goal_id == goal_id)
        )
        result = await self.db.execute(query)
        total = result.scalar()
        return float(total or 0)

    async def estimate_remaining_cost(
        self,
        goal_id: str,
        avg_cost_per_ticket: float | None = None
    ) -> dict[str, float]:
        """Estimate remaining cost to complete a goal."""
        # Get incomplete tickets
        query = select(func.count()).select_from(Ticket).where(
            Ticket.goal_id == goal_id,
            Ticket.state.in_(["todo", "planned", "executing", "blocked"])
        )
        result = await self.db.execute(query)
        remaining_tickets = result.scalar() or 0

        # Get average cost per ticket if not provided
        if avg_cost_per_ticket is None:
            summary = await self.get_cost_summary(days=30, goal_id=goal_id)
            if summary.session_count > 0:
                avg_cost_per_ticket = summary.avg_cost_per_session
            else:
                avg_cost_per_ticket = 0.50  # Default estimate

        spent = await self.get_goal_cost(goal_id)
        estimated_remaining = remaining_tickets * avg_cost_per_ticket

        return {
            "spent": round(spent, 2),
            "estimated_remaining": round(estimated_remaining, 2),
            "estimated_total": round(spent + estimated_remaining, 2),
            "remaining_tickets": remaining_tickets,
            "avg_cost_per_ticket": round(avg_cost_per_ticket, 4)
        }
