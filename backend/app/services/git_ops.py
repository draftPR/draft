"""Git operations for conflict detection and rebase support.

Provides conflict detection, rebase, continue/abort operations
that work with worktree-based branches.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ConflictState:
    """Current conflict state of a worktree or repo."""
    operation: str  # "rebase", "merge", "cherry_pick", "revert"
    conflicted_files: list[str] = field(default_factory=list)
    can_continue: bool = True
    can_abort: bool = True


@dataclass
class RebaseResult:
    """Result of a rebase operation."""
    success: bool
    message: str
    has_conflicts: bool = False
    conflicted_files: list[str] = field(default_factory=list)


def _run_git(
    args: list[str], cwd: Path, timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def detect_conflict_state(worktree_path: Path) -> ConflictState | None:
    """Detect if a worktree (or repo) is in a conflicted state.

    Checks for rebase-merge, rebase-apply, MERGE_HEAD, CHERRY_PICK_HEAD.

    Returns ConflictState if in conflict, None otherwise.
    """
    # Find the actual .git dir (worktrees use a .git file pointing to main repo)
    git_path = worktree_path / ".git"
    if git_path.is_file():
        # Worktree: .git is a file with "gitdir: <path>"
        gitdir_content = git_path.read_text().strip()
        if gitdir_content.startswith("gitdir: "):
            actual_git_dir = Path(gitdir_content[8:])
            if not actual_git_dir.is_absolute():
                actual_git_dir = (worktree_path / actual_git_dir).resolve()
        else:
            actual_git_dir = git_path
    elif git_path.is_dir():
        actual_git_dir = git_path
    else:
        return None

    operation = None

    # Check for rebase in progress
    if (actual_git_dir / "rebase-merge").is_dir():
        operation = "rebase"
    elif (actual_git_dir / "rebase-apply").is_dir():
        operation = "rebase"
    elif (actual_git_dir / "MERGE_HEAD").exists():
        operation = "merge"
    elif (actual_git_dir / "CHERRY_PICK_HEAD").exists():
        operation = "cherry_pick"
    elif (actual_git_dir / "REVERT_HEAD").exists():
        operation = "revert"

    if operation is None:
        # Also check for unmerged files (possible leftover conflict)
        conflicted = get_conflicted_files(worktree_path)
        if conflicted:
            return ConflictState(
                operation="unknown",
                conflicted_files=conflicted,
                can_continue=False,
                can_abort=False,
            )
        return None

    conflicted = get_conflicted_files(worktree_path)
    return ConflictState(
        operation=operation,
        conflicted_files=conflicted,
        can_continue=len(conflicted) == 0,
        can_abort=True,
    )


def get_conflicted_files(worktree_path: Path) -> list[str]:
    """Get list of files with unresolved conflicts."""
    try:
        result = _run_git(
            ["diff", "--name-only", "--diff-filter=U"],
            cwd=worktree_path,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return []


def rebase_branch(
    worktree_path: Path,
    onto_branch: str = "main",
) -> RebaseResult:
    """Rebase the current worktree branch onto another branch.

    Args:
        worktree_path: Path to the worktree
        onto_branch: Branch to rebase onto (default: main)

    Returns:
        RebaseResult with success/conflict info
    """
    logger.info(f"Rebasing worktree {worktree_path} onto {onto_branch}")

    # Fetch latest
    _run_git(["fetch", "origin"], cwd=worktree_path, timeout=30)

    result = _run_git(
        ["rebase", onto_branch],
        cwd=worktree_path,
        timeout=60,
    )

    if result.returncode == 0:
        return RebaseResult(
            success=True,
            message=f"Successfully rebased onto {onto_branch}",
        )

    # Check if it's a conflict
    conflicted = get_conflicted_files(worktree_path)
    if conflicted:
        return RebaseResult(
            success=False,
            message=f"Rebase conflicts in {len(conflicted)} file(s). Resolve conflicts and continue, or abort.",
            has_conflicts=True,
            conflicted_files=conflicted,
        )

    return RebaseResult(
        success=False,
        message=f"Rebase failed: {result.stderr.strip() or result.stdout.strip()}",
    )


def continue_rebase(worktree_path: Path) -> RebaseResult:
    """Continue a paused rebase after conflicts are resolved."""
    logger.info(f"Continuing rebase in {worktree_path}")

    # Stage all resolved files
    _run_git(["add", "--all"], cwd=worktree_path, timeout=10)

    result = _run_git(
        ["rebase", "--continue"],
        cwd=worktree_path,
        timeout=60,
    )

    if result.returncode == 0:
        return RebaseResult(
            success=True,
            message="Rebase completed successfully",
        )

    conflicted = get_conflicted_files(worktree_path)
    if conflicted:
        return RebaseResult(
            success=False,
            message=f"More conflicts found in {len(conflicted)} file(s)",
            has_conflicts=True,
            conflicted_files=conflicted,
        )

    return RebaseResult(
        success=False,
        message=f"Continue rebase failed: {result.stderr.strip()}",
    )


def abort_operation(worktree_path: Path) -> bool:
    """Abort the current conflict operation (rebase/merge/cherry-pick).

    Detects the current operation and runs the appropriate abort command.
    """
    state = detect_conflict_state(worktree_path)
    if not state:
        return True  # Nothing to abort

    logger.info(f"Aborting {state.operation} in {worktree_path}")

    abort_commands = {
        "rebase": ["rebase", "--abort"],
        "merge": ["merge", "--abort"],
        "cherry_pick": ["cherry-pick", "--abort"],
        "revert": ["revert", "--abort"],
    }

    cmd = abort_commands.get(state.operation)
    if not cmd:
        logger.warning(f"Unknown operation to abort: {state.operation}")
        return False

    result = _run_git(cmd, cwd=worktree_path, timeout=30)
    if result.returncode != 0:
        logger.error(f"Abort failed: {result.stderr}")
        return False

    return True


@dataclass
class PushResult:
    """Result of a push operation."""
    success: bool
    message: str


def push_branch(
    repo_path: Path,
    branch: str,
    remote: str = "origin",
) -> PushResult:
    """Push a branch to the remote.

    Args:
        repo_path: Path to the repo or worktree
        branch: Branch name to push
        remote: Remote name (default: origin)

    Returns:
        PushResult with success/error info
    """
    logger.info(f"Pushing {branch} to {remote}")

    result = _run_git(
        ["push", "-u", remote, branch],
        cwd=repo_path,
        timeout=60,
    )

    if result.returncode == 0:
        return PushResult(
            success=True,
            message=f"Successfully pushed {branch} to {remote}",
        )

    return PushResult(
        success=False,
        message=f"Push failed: {result.stderr.strip() or result.stdout.strip()}",
    )


def force_push_branch(
    repo_path: Path,
    branch: str,
    remote: str = "origin",
) -> PushResult:
    """Force-push a branch using --force-with-lease for safety.

    Args:
        repo_path: Path to the repo or worktree
        branch: Branch name to push
        remote: Remote name (default: origin)

    Returns:
        PushResult with success/error info
    """
    logger.info(f"Force-pushing {branch} to {remote} (--force-with-lease)")

    result = _run_git(
        ["push", "--force-with-lease", remote, branch],
        cwd=repo_path,
        timeout=60,
    )

    if result.returncode == 0:
        return PushResult(
            success=True,
            message=f"Successfully force-pushed {branch} to {remote}",
        )

    return PushResult(
        success=False,
        message=f"Force-push failed: {result.stderr.strip() or result.stdout.strip()}",
    )


def get_push_status(
    repo_path: Path, branch: str, remote: str = "origin"
) -> dict:
    """Check if local branch is ahead/behind the remote tracking branch.

    Returns dict with ahead/behind counts relative to remote.
    """
    # Fetch latest remote state
    _run_git(["fetch", remote], cwd=repo_path, timeout=30)

    remote_branch = f"{remote}/{branch}"

    # Check if remote branch exists
    check = _run_git(
        ["rev-parse", "--verify", remote_branch],
        cwd=repo_path,
        timeout=10,
    )
    if check.returncode != 0:
        return {
            "ahead": 0,
            "behind": 0,
            "remote_exists": False,
            "needs_push": True,
        }

    behind_result = _run_git(
        ["rev-list", "--count", f"{branch}..{remote_branch}"],
        cwd=repo_path,
        timeout=10,
    )
    behind = int(behind_result.stdout.strip()) if behind_result.returncode == 0 else 0

    ahead_result = _run_git(
        ["rev-list", "--count", f"{remote_branch}..{branch}"],
        cwd=repo_path,
        timeout=10,
    )
    ahead = int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0

    return {
        "ahead": ahead,
        "behind": behind,
        "remote_exists": True,
        "needs_push": ahead > 0,
    }


def get_divergence_info(
    repo_path: Path, branch_name: str, target_branch: str = "main"
) -> dict:
    """Get divergence info between two branches.

    Returns dict with ahead/behind counts.
    """
    # Commits in target not in branch (branch is behind)
    behind_result = _run_git(
        ["rev-list", "--count", f"{branch_name}..{target_branch}"],
        cwd=repo_path,
        timeout=10,
    )
    behind = int(behind_result.stdout.strip()) if behind_result.returncode == 0 else 0

    # Commits in branch not in target (branch is ahead)
    ahead_result = _run_git(
        ["rev-list", "--count", f"{target_branch}..{branch_name}"],
        cwd=repo_path,
        timeout=10,
    )
    ahead = int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0

    return {
        "ahead": ahead,
        "behind": behind,
        "diverged": behind > 0 and ahead > 0,
        "up_to_date": behind == 0,
    }
