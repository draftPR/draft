"""Tests for the sync planner unblock logic (_unblock_ready_tickets_sync)."""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.state_machine import TicketState


def _make_sync_session() -> Session:
    """Create an in-memory sync session with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def _seed(db: Session):
    """Seed a board, goal, a blocker ticket, and a blocked ticket."""
    board = Board(id=str(uuid.uuid4()), name="test", repo_root="/tmp/repo")
    db.add(board)
    db.flush()

    goal = Goal(id=str(uuid.uuid4()), board_id=board.id, title="Test goal")
    db.add(goal)
    db.flush()

    blocker = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Blocker ticket",
        state=TicketState.DONE.value,
    )
    db.add(blocker)
    db.flush()

    blocked = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Blocked ticket",
        state=TicketState.BLOCKED.value,
        blocked_by_ticket_id=blocker.id,
    )
    db.add(blocked)
    db.flush()

    return board, goal, blocker, blocked


def test_unblock_when_blocker_is_done():
    """Blocked ticket should transition to PLANNED when its blocker is DONE."""
    from app.services.planner_tick_sync import _unblock_ready_tickets_sync

    db = _make_sync_session()
    _board, _goal, _blocker, blocked = _seed(db)
    db.commit()

    count = _unblock_ready_tickets_sync(db)

    assert count == 1
    db.refresh(blocked)
    assert blocked.state == TicketState.PLANNED.value

    # Verify a TRANSITIONED event was created
    events = db.query(TicketEvent).filter_by(ticket_id=blocked.id).all()
    assert len(events) == 1
    assert events[0].from_state == TicketState.BLOCKED.value
    assert events[0].to_state == TicketState.PLANNED.value
    assert "Unblocked" in events[0].reason


def test_no_unblock_when_blocker_not_done():
    """Blocked ticket should stay BLOCKED when its blocker is still executing."""
    from app.services.planner_tick_sync import _unblock_ready_tickets_sync

    db = _make_sync_session()
    _board, _goal, blocker, blocked = _seed(db)

    # Override blocker to EXECUTING (not done yet)
    blocker.state = TicketState.EXECUTING.value
    db.commit()

    count = _unblock_ready_tickets_sync(db)

    assert count == 0
    db.refresh(blocked)
    assert blocked.state == TicketState.BLOCKED.value


def test_no_unblock_for_blocked_without_dependency():
    """BLOCKED ticket without blocked_by_ticket_id should not be touched."""
    from app.services.planner_tick_sync import _unblock_ready_tickets_sync

    db = _make_sync_session()
    board = Board(id=str(uuid.uuid4()), name="test", repo_root="/tmp/repo")
    db.add(board)
    db.flush()

    goal = Goal(id=str(uuid.uuid4()), board_id=board.id, title="Test goal")
    db.add(goal)
    db.flush()

    # Blocked by failure, NOT by another ticket
    ticket = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Failed ticket",
        state=TicketState.BLOCKED.value,
        blocked_by_ticket_id=None,
    )
    db.add(ticket)
    db.commit()

    count = _unblock_ready_tickets_sync(db)

    assert count == 0
    db.refresh(ticket)
    assert ticket.state == TicketState.BLOCKED.value


def test_unblock_multiple_tickets():
    """Multiple tickets blocked by the same done ticket should all unblock."""
    from app.services.planner_tick_sync import _unblock_ready_tickets_sync

    db = _make_sync_session()
    board = Board(id=str(uuid.uuid4()), name="test", repo_root="/tmp/repo")
    db.add(board)
    db.flush()

    goal = Goal(id=str(uuid.uuid4()), board_id=board.id, title="Test goal")
    db.add(goal)
    db.flush()

    blocker = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Blocker",
        state=TicketState.DONE.value,
    )
    db.add(blocker)
    db.flush()

    blocked_1 = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Blocked 1",
        state=TicketState.BLOCKED.value,
        blocked_by_ticket_id=blocker.id,
    )
    blocked_2 = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="Blocked 2",
        state=TicketState.BLOCKED.value,
        blocked_by_ticket_id=blocker.id,
    )
    db.add_all([blocked_1, blocked_2])
    db.commit()

    count = _unblock_ready_tickets_sync(db)

    assert count == 2
    db.refresh(blocked_1)
    db.refresh(blocked_2)
    assert blocked_1.state == TicketState.PLANNED.value
    assert blocked_2.state == TicketState.PLANNED.value
