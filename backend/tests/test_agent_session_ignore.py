"""Saving a session must not touch tracked files in the ticket worktree.

It used to append `/.draft/` to the worktree's `.gitignore`, so every revision
diff carried a change the agent never made and the "no changes" check never
fired. The rule now lives in the repo's info/exclude.
"""

import subprocess
from pathlib import Path

from app.services.agent_session_service import AgentSessionService


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_save_session_leaves_worktree_clean(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "ticket", str(worktree))

    service = AgentSessionService(worktree)
    service.save_session("sess-1", "ticket-1")
    service.save_session("sess-1", "ticket-1")

    assert _git(worktree, "status", "--porcelain") == ""
    assert (worktree / ".draft" / "agent_session.json").exists()
    assert not (worktree / ".gitignore").exists()
    exclude = (repo / ".git" / "info" / "exclude").read_text()
    assert exclude.splitlines().count("/.draft/") == 1
