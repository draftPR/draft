"""End-to-end split completion on a real git repo and a temp SQLite file.

Covers: children branch from the parent branch, merge back in split order,
revision recorded on the parent, parent -> VERIFYING with verify enqueued,
children worktrees/branches cleaned up.
"""

import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.services.split_completion as split_completion
import app.worker as worker
from app.models.base import Base
from app.models.board import Board
from app.models.goal import Goal
from app.models.revision import Revision
from app.models.ticket import Ticket
from app.models.workspace import Workspace
from app.services.workspace_service import WorkspaceService
from app.state_machine import TicketState


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def test_complete_split_parent_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DRAFT_DATA_DIR", str(tmp_path / "data"))
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "t@t")

    # Real repo with a base commit on main
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    # Temp file DB shared by every session (worker helpers open their own)
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    @contextmanager
    def fake_sync_db():
        db = factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(split_completion, "get_sync_db", fake_sync_db)
    monkeypatch.setattr(worker, "get_sync_db", fake_sync_db)
    verify_calls: list[str] = []
    monkeypatch.setattr(
        worker, "_enqueue_verify_job_sync", lambda tid: verify_calls.append(tid)
    )

    with fake_sync_db() as db:
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
            title="Big feature",
            state=TicketState.BLOCKED.value,
        )
        db.add(parent)
        db.flush()
        ws = WorkspaceService(db)
        parent_ws = ws.create_worktree(parent.id, goal.id)
        parent_branch = parent_ws.branch_name
        # Parent branch diverges from main so we can prove children fork from it
        (Path(parent_ws.worktree_path) / "PARENT.txt").write_text("parent\n")
        _git(Path(parent_ws.worktree_path), "add", "-A")
        _git(Path(parent_ws.worktree_path), "commit", "-q", "-m", "parent prep")

        child_ids = []
        for i in range(2):
            child = Ticket(
                id=str(uuid.uuid4()),
                board_id=board.id,
                goal_id=goal.id,
                parent_ticket_id=parent.id,
                title=f"part {i}",
                state=TicketState.DONE.value,
                sort_order=i,
            )
            db.add(child)
            db.flush()
            child_ws = ws.create_worktree(child.id, goal.id)
            cwt = Path(child_ws.worktree_path)
            assert (cwt / "PARENT.txt").exists(), "child must fork from parent branch"
            (cwt / f"part{i}.txt").write_text(f"work {i}\n")
            _git(cwt, "add", "-A")
            _git(cwt, "commit", "-q", "-m", f"part {i} done")
            child_ids.append(child.id)
        db.commit()
        parent_id = parent.id

    assert split_completion.complete_split_parents_sync() == 1

    with fake_sync_db() as db:
        parent = db.get(Ticket, parent_id)
        assert parent.state == TicketState.VERIFYING.value
        assert verify_calls == [parent_id]
        revs = db.execute(select(Revision).where(Revision.ticket_id == parent_id))
        assert len(revs.scalars().all()) == 1
        for cid in child_ids:
            cws = db.execute(
                select(Workspace).where(Workspace.ticket_id == cid)
            ).scalar_one()
            assert cws.cleaned_up_at is not None

    parent_wt = Path(parent_ws.worktree_path)
    assert (parent_wt / "part0.txt").exists() and (parent_wt / "part1.txt").exists()
    subjects = _git(parent_wt, "log", "--format=%s", "-3").splitlines()
    assert subjects[:2] == ["Merge sub-ticket: part 1", "Merge sub-ticket: part 0"]
    branches = _git(repo, "branch", "--list", "goal/*")
    assert parent_branch in branches
    assert "ticket/" + child_ids[0] not in branches
