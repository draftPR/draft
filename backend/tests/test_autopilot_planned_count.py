"""Autopilot stop condition: dependency-blocked tickets are not pending work."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.routers.planner import count_planned_tickets
from app.state_machine import TicketState


async def _seed(db: AsyncSession, blocker_state: str) -> None:
    board = Board(id=str(uuid.uuid4()), name="b", repo_root="/tmp/r")
    db.add(board)
    await db.flush()
    goal = Goal(id=str(uuid.uuid4()), board_id=board.id, title="g")
    db.add(goal)
    await db.flush()

    blocker = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="blocker",
        state=blocker_state,
    )
    free = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="free",
        state=TicketState.PLANNED.value,
    )
    db.add_all([blocker, free])
    await db.flush()
    db.add(
        Ticket(
            id=str(uuid.uuid4()),
            board_id=board.id,
            goal_id=goal.id,
            title="dependent",
            state=TicketState.PLANNED.value,
            blocked_by_ticket_id=blocker.id,
        )
    )
    await db.flush()


async def test_blocked_ticket_is_not_counted_as_runnable(db: AsyncSession):
    # blocker still in progress -> dependent is waiting, only "free" is runnable
    await _seed(db, TicketState.NEEDS_HUMAN.value)
    runnable, waiting = await count_planned_tickets(db)
    assert (runnable, waiting) == (1, 1)


async def test_done_blocker_makes_dependent_runnable(db: AsyncSession):
    await _seed(db, TicketState.DONE.value)
    runnable, waiting = await count_planned_tickets(db)
    assert (runnable, waiting) == (2, 0)
