"""Split completion: readiness detection (in-memory DB) and git merge helper."""

import json
import subprocess
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.git_ops import merge_branch
from app.services.split_completion import find_ready_split_parents
from app.state_machine import ActorType, EventType, TicketState


@contextmanager
def _mem_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()


def _seed_parent(db, child_states: list[str]) -> str:
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
        title="parent",
        state=TicketState.BLOCKED.value,
    )
    db.add(parent)
    db.flush()
    for i, state in enumerate(child_states):
        db.add(
            Ticket(
                id=str(uuid.uuid4()),
                board_id=board.id,
                goal_id=goal.id,
                parent_ticket_id=parent.id,
                title=f"child {i}",
                state=state,
                sort_order=len(child_states) - i,  # reverse, to test ordering
            )
        )
    db.commit()
    return parent.id


def test_ready_when_all_children_done():
    with _mem_db() as db:
        pid = _seed_parent(db, ["done", "done"])
        ready = find_ready_split_parents(db)
        assert [p for p, _ in ready] == [pid]
        # ordered by sort_order ascending -> "child 1" (sort 1) before "child 0"
        kids = [db.get(Ticket, cid).title for cid in ready[0][1]]
        assert kids == ["child 1", "child 0"]


def test_not_ready_with_pending_child():
    with _mem_db() as db:
        _seed_parent(db, ["done", "needs_human"])
        assert find_ready_split_parents(db) == []


def test_recent_failure_is_skipped_then_retried():
    with _mem_db() as db:
        pid = _seed_parent(db, ["done"])
        ev = TicketEvent(
            ticket_id=pid,
            event_type=EventType.COMMENT.value,
            from_state="blocked",
            to_state="blocked",
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason="Sub-ticket merge failed: conflict",
            payload_json=json.dumps({"split_merge_failed": True}),
        )
        db.add(ev)
        db.commit()
        assert find_ready_split_parents(db) == []

        ev.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        db.commit()
        assert [p for p, _ in find_ready_split_parents(db)] == [pid]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _repo_with_child_branch(tmp_path: Path, conflicting: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "child")
    (repo / ("f.txt" if conflicting else "g.txt")).write_text("child\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "child work")
    _git(repo, "checkout", "-q", "main")
    if conflicting:
        (repo / "f.txt").write_text("parent\n")
        _git(repo, "commit", "-q", "-am", "parent work")
    return repo


def test_merge_branch_success(tmp_path: Path):
    repo = _repo_with_child_branch(tmp_path, conflicting=False)
    res = merge_branch(repo, "child", "Merge sub-ticket: child")
    assert res.success, res.message
    assert (repo / "g.txt").read_text() == "child\n"
    assert "Merge sub-ticket: child" in _git(repo, "log", "-1", "--format=%s")


def test_merge_branch_conflict_aborts_cleanly(tmp_path: Path):
    repo = _repo_with_child_branch(tmp_path, conflicting=True)
    res = merge_branch(repo, "child", "Merge sub-ticket: child")
    assert not res.success
    assert res.conflicted_files == ["f.txt"]
    assert _git(repo, "status", "--porcelain") == ""
    assert (repo / "f.txt").read_text() == "parent\n"
