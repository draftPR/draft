"""create_child_tickets_sync against an in-memory sync DB (Nadir mocked)."""

import json
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services import split_service
from app.services.config_service import DraftConfig, ExecutorProfile
from app.services.routing_service import RoutingDecision
from app.services.split_service import parse_subtasks
from app.state_machine import TicketState

SUBTASKS = {
    "subtasks": [
        {"title": "Add model", "description": "Add column", "complexity": "simple"},
        {
            "title": "Wire API",
            "description": "Expose it",
            "blocked_by": "Add model",
            "complexity": "medium",
        },
    ]
}


def test_create_child_tickets_sync(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def fake_sync_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(split_service, "get_sync_db", fake_sync_db)
    # First child routes to a defined profile; second to an unknown one,
    # which must fall back to the board default (None).
    decisions = iter(
        [
            RoutingDecision(profile="claude-opus", tier="complex", confidence=0.9),
            RoutingDecision(profile="ghost", tier="simple", confidence=0.5),
        ]
    )
    monkeypatch.setattr(split_service, "route_ticket", lambda *a, **k: next(decisions))

    with fake_sync_db() as db:
        board = Board(id=str(uuid.uuid4()), name="b", repo_root="/tmp/r")
        db.add(board)
        db.flush()
        goal = Goal(id=str(uuid.uuid4()), board_id=board.id, title="g")
        db.add(goal)
        db.flush()
        parent = Ticket(
            id=str(uuid.uuid4()),
            board_id=board.id,
            goal_id=goal.id,
            title="Big ticket",
            state=TicketState.EXECUTING.value,
            priority=70,
        )
        db.add(parent)
        db.commit()
        parent_id = parent.id

    config = DraftConfig(
        executor_profiles={"claude-opus": ExecutorProfile(name="claude-opus")}
    )
    subs = parse_subtasks(json.dumps(SUBTASKS), max_children=6)
    ids = split_service.create_child_tickets_sync(parent_id, subs, config)

    with fake_sync_db() as db:
        kids = [db.get(Ticket, i) for i in ids]
        assert [k.title for k in kids] == ["Add model", "Wire API"]
        assert all(k.parent_ticket_id == parent_id for k in kids)
        assert all(k.state == TicketState.PLANNED.value for k in kids)
        assert all(k.priority == 70 for k in kids)
        assert kids[1].blocked_by_ticket_id == kids[0].id
        assert kids[0].executor_profile == "claude-opus"
        assert kids[1].executor_profile is None
        parent_events = db.query(TicketEvent).filter_by(ticket_id=parent_id).all()
        assert any("Split into 2" in (e.reason or "") for e in parent_events)
