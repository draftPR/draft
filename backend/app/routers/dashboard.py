"""Dashboard and metrics API endpoints."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_session import AgentSession
from app.models.ticket import Ticket
from app.state_machine import TicketState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ============================================================================
# Response Models
# ============================================================================


class BudgetStatus(BaseModel):
    """Budget tracking status."""

    daily_budget: float | None = None
    daily_spent: float = 0
    daily_remaining: float = 0
    weekly_budget: float | None = None
    weekly_spent: float = 0
    weekly_remaining: float = 0
    monthly_budget: float | None = None
    monthly_spent: float = 0
    monthly_remaining: float = 0
    is_over_budget: bool = False
    warning_threshold_reached: bool = False


class SprintMetrics(BaseModel):
    """Sprint progress metrics."""

    total_tickets: int = 0
    completed_tickets: int = 0
    in_progress_tickets: int = 0
    blocked_tickets: int = 0
    completion_rate: float = 0
    avg_cycle_time_hours: float = 0
    velocity: float = 0  # tickets per day


class AgentMetrics(BaseModel):
    """AI agent usage metrics."""

    total_sessions: int = 0
    successful_sessions: int = 0
    success_rate: float = 0
    avg_turns_per_session: float = 0
    most_used_agent: str = "claude"
    total_cost_usd: float = 0


class CostTrendItem(BaseModel):
    """Daily cost trend item."""

    date: str
    cost: float


class DashboardResponse(BaseModel):
    """Complete dashboard data."""

    budget: BudgetStatus
    sprint: SprintMetrics
    agent: AgentMetrics
    cost_trend: list[CostTrendItem] = Field(default_factory=list)


# ============================================================================
# Helper Functions
# ============================================================================


async def get_period_cost(
    db: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    goal_id: str | None = None,
) -> float:
    """Get total cost for a time period."""
    query = select(func.coalesce(func.sum(AgentSession.estimated_cost_usd), 0)).where(
        AgentSession.created_at >= start_date, AgentSession.created_at < end_date
    )

    if goal_id:
        query = query.join(Ticket).where(Ticket.goal_id == goal_id)

    result = await db.execute(query)
    return float(result.scalar() or 0)


async def get_budget_status(
    db: AsyncSession,
    goal_id: str | None = None,
    daily_budget: float = 10.0,
    weekly_budget: float = 50.0,
    monthly_budget: float = 150.0,
) -> BudgetStatus:
    """Calculate budget status for all periods."""
    now = datetime.utcnow()

    # Daily
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_spent = await get_period_cost(
        db, day_start, day_start + timedelta(days=1), goal_id
    )

    # Weekly (Monday start)
    week_start = day_start - timedelta(days=day_start.weekday())
    weekly_spent = await get_period_cost(
        db, week_start, week_start + timedelta(weeks=1), goal_id
    )

    # Monthly
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    monthly_spent = await get_period_cost(db, month_start, month_end, goal_id)

    is_over = (
        daily_spent > daily_budget
        or weekly_spent > weekly_budget
        or monthly_spent > monthly_budget
    )

    warning = (
        daily_spent >= daily_budget * 0.8
        or weekly_spent >= weekly_budget * 0.8
        or monthly_spent >= monthly_budget * 0.8
    )

    return BudgetStatus(
        daily_budget=daily_budget,
        daily_spent=round(daily_spent, 2),
        daily_remaining=round(max(0, daily_budget - daily_spent), 2),
        weekly_budget=weekly_budget,
        weekly_spent=round(weekly_spent, 2),
        weekly_remaining=round(max(0, weekly_budget - weekly_spent), 2),
        monthly_budget=monthly_budget,
        monthly_spent=round(monthly_spent, 2),
        monthly_remaining=round(max(0, monthly_budget - monthly_spent), 2),
        is_over_budget=is_over,
        warning_threshold_reached=warning,
    )


async def get_sprint_metrics(
    db: AsyncSession, goal_id: str | None = None
) -> SprintMetrics:
    """Calculate sprint progress metrics."""
    base_query = select(Ticket)
    if goal_id:
        base_query = base_query.where(Ticket.goal_id == goal_id)

    result = await db.execute(base_query)
    tickets = result.scalars().all()

    if not tickets:
        return SprintMetrics()

    total = len(tickets)
    completed = sum(1 for t in tickets if t.state == TicketState.DONE.value)
    in_progress = sum(
        1
        for t in tickets
        if t.state
        in [
            TicketState.EXECUTING.value,
            TicketState.VERIFYING.value,
            TicketState.NEEDS_HUMAN.value,
        ]
    )
    blocked = sum(1 for t in tickets if t.state == TicketState.BLOCKED.value)

    # Calculate velocity (tickets completed in last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    completed_recently = sum(
        1
        for t in tickets
        if t.state == TicketState.DONE.value and t.updated_at >= week_ago
    )
    velocity = completed_recently / 7.0

    # Average cycle time (from created to done)
    done_tickets = [t for t in tickets if t.state == TicketState.DONE.value]
    if done_tickets:
        cycle_times = [
            (t.updated_at - t.created_at).total_seconds() / 3600 for t in done_tickets
        ]
        avg_cycle = sum(cycle_times) / len(cycle_times)
    else:
        avg_cycle = 0

    return SprintMetrics(
        total_tickets=total,
        completed_tickets=completed,
        in_progress_tickets=in_progress,
        blocked_tickets=blocked,
        completion_rate=round((completed / total) * 100, 1) if total > 0 else 0,
        avg_cycle_time_hours=round(avg_cycle, 1),
        velocity=round(velocity, 1),
    )


async def get_agent_metrics(
    db: AsyncSession, goal_id: str | None = None
) -> AgentMetrics:
    """Calculate AI agent usage metrics using SQL aggregation."""
    # Build base filter condition
    filters = []
    if goal_id:
        filters.append(Ticket.goal_id == goal_id)

    # Aggregate totals in a single query
    totals_query = select(
        func.count(AgentSession.id).label("total"),
        func.count(AgentSession.ended_at)
        .filter(AgentSession.turn_count > 0)
        .label("successful"),
        func.coalesce(func.avg(AgentSession.turn_count), 0).label("avg_turns"),
        func.coalesce(func.sum(AgentSession.estimated_cost_usd), 0).label(
            "total_cost"
        ),
    )
    if goal_id:
        totals_query = totals_query.join(Ticket).where(Ticket.goal_id == goal_id)

    totals_result = await db.execute(totals_query)
    row = totals_result.one()
    total = row.total
    successful = row.successful
    avg_turns = float(row.avg_turns)
    total_cost = float(row.total_cost)

    if total == 0:
        return AgentMetrics()

    # Most used agent via GROUP BY
    agent_query = select(
        AgentSession.agent_type, func.count(AgentSession.id).label("cnt")
    ).group_by(AgentSession.agent_type)
    if goal_id:
        agent_query = agent_query.join(Ticket).where(Ticket.goal_id == goal_id)
    agent_query = agent_query.order_by(func.count(AgentSession.id).desc()).limit(1)

    agent_result = await db.execute(agent_query)
    agent_row = agent_result.first()
    most_used = agent_row[0] if agent_row else "claude"

    return AgentMetrics(
        total_sessions=total,
        successful_sessions=successful,
        success_rate=round((successful / total) * 100, 1) if total > 0 else 0,
        avg_turns_per_session=round(avg_turns, 1),
        most_used_agent=most_used,
        total_cost_usd=round(total_cost, 2),
    )


async def get_cost_trend(
    db: AsyncSession, days: int = 7, goal_id: str | None = None
) -> list[CostTrendItem]:
    """Get daily cost trend for the last N days."""
    trends = []
    now = datetime.utcnow()

    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        cost = await get_period_cost(db, day_start, day_end, goal_id)

        trends.append(
            CostTrendItem(
                date=day_start.strftime("%a"),  # Mon, Tue, etc.
                cost=round(cost, 2),
            )
        )

    return trends


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    goal_id: str | None = Query(None, description="Filter by goal ID"),
    daily_budget: float = Query(10.0, description="Daily budget limit"),
    weekly_budget: float = Query(50.0, description="Weekly budget limit"),
    monthly_budget: float = Query(150.0, description="Monthly budget limit"),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Get complete dashboard data with metrics and budget status."""
    budget = await get_budget_status(
        db, goal_id, daily_budget, weekly_budget, monthly_budget
    )
    sprint = await get_sprint_metrics(db, goal_id)
    agent = await get_agent_metrics(db, goal_id)
    cost_trend = await get_cost_trend(db, 7, goal_id)

    return DashboardResponse(
        budget=budget, sprint=sprint, agent=agent, cost_trend=cost_trend
    )


@router.get("/budget", response_model=BudgetStatus)
async def get_budget(
    goal_id: str | None = Query(None, description="Filter by goal ID"),
    daily_budget: float = Query(10.0),
    weekly_budget: float = Query(50.0),
    monthly_budget: float = Query(150.0),
    db: AsyncSession = Depends(get_db),
) -> BudgetStatus:
    """Get current budget status."""
    return await get_budget_status(
        db, goal_id, daily_budget, weekly_budget, monthly_budget
    )


@router.get("/sprint", response_model=SprintMetrics)
async def get_sprint(
    goal_id: str | None = Query(None, description="Filter by goal ID"),
    db: AsyncSession = Depends(get_db),
) -> SprintMetrics:
    """Get sprint progress metrics."""
    return await get_sprint_metrics(db, goal_id)


@router.get("/agent-metrics", response_model=AgentMetrics)
async def get_agents(
    goal_id: str | None = Query(None, description="Filter by goal ID"),
    db: AsyncSession = Depends(get_db),
) -> AgentMetrics:
    """Get AI agent usage metrics."""
    return await get_agent_metrics(db, goal_id)
