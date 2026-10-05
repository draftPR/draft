"""A sub-ticket branches from its finished blocker, not just from the parent.

Without this the dependent agent starts from a worktree that lacks its
dependency's code, re-implements it, and the two branches collide when the
parent merges them.
"""

import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import worker
from app.models.base import Base
from app.models.board import Board
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.services.workspace_service import WorkspaceService
from app.state_machine import TicketState


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _child(db, board, goal, parent, title, blocker=None, state="planned"):
    t = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        parent_ticket_id=parent.id,
        title=title,
        state=state,
        blocked_by_ticket_id=blocker.id if blocker else None,
    )
    db.add(t)
    db.flush()
    return t


def _split(tmp_path: Path, monkeypatch):
    """Repo + board + goal + split parent with its own worktree."""
    monkeypatch.setenv("DRAFT_DATA_DIR", str(tmp_path / "data"))
    repo = _repo(tmp_path)
    db = _session()

    board = Board(id=str(uuid.uuid4()), name="b", repo_root=str(repo))
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

    ws = WorkspaceService(db)
    parent_wt = Path(ws.create_worktree(parent.id, goal.id).worktree_path)
    return db, ws, board, goal, parent, parent_wt


def _commit(wt: Path, name: str) -> None:
    (wt / name).write_text(f"{name}\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", name)


def _done_api(db, ws, board, goal, parent) -> Ticket:
    """Finished sub-ticket that committed endpoint.py."""
    api = _child(db, board, goal, parent, "api", state=TicketState.DONE.value)
    _commit(Path(ws.create_worktree(api.id, goal.id).worktree_path), "endpoint.py")
    db.commit()
    return api


def test_dependent_subticket_starts_from_its_blocker(tmp_path: Path, monkeypatch):
    db, ws, board, goal, parent, _ = _split(tmp_path, monkeypatch)
    api = _done_api(db, ws, board, goal, parent)

    # Dependent sub-ticket must see the blocker's file in its own worktree.
    tests = _child(db, board, goal, parent, "tests", blocker=api)
    tests_wt = Path(ws.create_worktree(tests.id, goal.id).worktree_path)
    db.commit()

    assert (tests_wt / "endpoint.py").exists(), (
        "dependent sub-ticket must branch from its finished blocker"
    )


def test_dependent_subticket_diff_excludes_blocker_work(tmp_path: Path, monkeypatch):
    db, ws, board, goal, parent, _ = _split(tmp_path, monkeypatch)
    api = _done_api(db, ws, board, goal, parent)
    tests = _child(db, board, goal, parent, "tests", blocker=api)
    tests_wt = Path(ws.create_worktree(tests.id, goal.id).worktree_path)
    _commit(tests_wt, "check_api.py")
    db.commit()

    @contextmanager
    def same_db():
        yield db

    monkeypatch.setattr(worker, "get_sync_db", same_db)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _, _, _, stat, has_changes = worker.capture_git_diff(
        cwd=tests_wt,
        evidence_dir=evidence,
        evidence_id="e",
        repo_root=Path(board.repo_root),
        ticket_id=tests.id,
    )

    assert has_changes
    assert "check_api.py" in stat
    assert "endpoint.py" not in stat, "blocker's work is not this ticket's diff"


def test_blocker_outside_the_split_is_ignored(tmp_path: Path, monkeypatch):
    db, ws, board, goal, parent, _ = _split(tmp_path, monkeypatch)
    other = Ticket(
        id=str(uuid.uuid4()),
        board_id=board.id,
        goal_id=goal.id,
        title="unrelated",
        state=TicketState.DONE.value,
    )
    db.add(other)
    db.flush()
    _commit(Path(ws.create_worktree(other.id, goal.id).worktree_path), "OTHER.txt")
    db.commit()

    child = _child(db, board, goal, parent, "child", blocker=other)
    child_wt = Path(ws.create_worktree(child.id, goal.id).worktree_path)
    db.commit()

    assert not (child_wt / "OTHER.txt").exists()


def test_subticket_without_blocker_starts_from_parent(tmp_path: Path, monkeypatch):
    db, ws, board, goal, parent, parent_wt = _split(tmp_path, monkeypatch)
    _commit(parent_wt, "PARENT.txt")
    db.commit()

    free = _child(db, board, goal, parent, "free")
    free_wt = Path(ws.create_worktree(free.id, goal.id).worktree_path)
    db.commit()

    assert (free_wt / "PARENT.txt").exists()
