"""Delivery status for a goal (ticket state rollup).

The former end-to-end ``DeliveryPipeline`` orchestrator was removed: it was
never wired to the job system (called nonexistent ``Job.job_type`` and a
``create_job`` signature that does not exist). Goal execution ordering lives
in the planner (``planner_tick_sync``) and the ticket DAG.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.state_machine import TicketState


async def get_pipeline_status(db: AsyncSession, goal_id: str) -> dict[str, Any]:
    """Get the current status of the delivery pipeline for a goal.

    Returns:
        Dict with pipeline status, progress, and blocking issues
    """
    result = await db.execute(select(Ticket).where(Ticket.goal_id == goal_id))
    tickets = list(result.scalars().all())

    if not tickets:
        return {"status": "not_started", "reason": "No tickets generated yet"}

    state_counts: dict[str, int] = {}
    for ticket in tickets:
        state = ticket.state
        state_counts[state] = state_counts.get(state, 0) + 1

    total = len(tickets)
    completed = state_counts.get(TicketState.DONE.value, 0)
    blocked = state_counts.get(TicketState.BLOCKED.value, 0)
    executing = state_counts.get(TicketState.EXECUTING.value, 0) + state_counts.get(
        TicketState.VERIFYING.value, 0
    )

    if blocked > 0:
        status = "blocked"
    elif executing > 0:
        status = "in_progress"
    elif completed == total:
        status = "ready_for_merge"
    else:
        status = "ready_to_execute"

    return {
        "status": status,
        "total_tickets": total,
        "completed": completed,
        "blocked": blocked,
        "executing": executing,
        "progress_percent": int((completed / total) * 100) if total > 0 else 0,
        "state_breakdown": state_counts,
    }
