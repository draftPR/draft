"""Simple git merge operations without state machine coupling.

This module provides straightforward git merge operations that can be called
from any context without requiring specific ticket states or validation.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SimpleMergeResult:
    """Result of a simple git merge operation."""
    success: bool
    message: str
    merged_branch: str | None = None
    target_branch: str | None = None
    merge_commit: str | None = None


class GitMergeError(Exception):
    """Raised when git merge operations fail."""
    pass


def git_merge_worktree_branch(
    repo_path: Path,
    branch_name: str,
    target_branch: str = "main",
    delete_branch_after: bool = True,
    push_to_remote: bool = False,
    squash: bool = False,
    check_divergence: bool = True,
) -> SimpleMergeResult:
    """Merge a worktree branch into the target branch.

    This is a simple, synchronous git merge operation with no state validation
    or database coupling. It just runs git commands.

    Args:
        repo_path: Path to the main git repository (not the worktree)
        branch_name: Name of the branch to merge (e.g., "goal/xxx/ticket/yyy")
        target_branch: Target branch to merge into (default: "main")
        delete_branch_after: Whether to delete the branch after merge
        push_to_remote: Whether to push to remote after merge
        squash: Whether to squash commits (single commit per task)
        check_divergence: Whether to check if base branch moved ahead

    Returns:
        SimpleMergeResult with success status and details

    Raises:
        GitMergeError: If git operations fail
    """
    logger.info(f"Starting simple merge: {branch_name} -> {target_branch} (squash={squash})")

    try:
        # 1. Ensure we're in the repo (not a worktree)
        if not (repo_path / ".git").exists():
            raise GitMergeError(f"Not a git repository: {repo_path}")

        # 2. Fetch latest (if remote exists)
        logger.info("Fetching latest from remote...")
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"Git fetch failed (may not have remote): {result.stderr}")

        # 3. Divergence check (copied from Vibe Kanban!)
        if check_divergence:
            logger.info("Checking for divergence...")
            # Count commits in target_branch that are not in branch_name
            result = subprocess.run(
                ["git", "rev-list", "--count", f"{branch_name}..{target_branch}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                commits_behind = int(result.stdout.strip())
                if commits_behind > 0:
                    raise GitMergeError(
                        f"Cannot merge: {target_branch} is {commits_behind} commits ahead of {branch_name}. "
                        f"The base branch has moved forward since the task was created. "
                        f"Rebase the task branch onto {target_branch} first."
                    )
                logger.info("✓ No divergence detected")
            else:
                logger.warning(f"Divergence check failed: {result.stderr}")

        # 4. Checkout target branch
        logger.info(f"Checking out {target_branch}...")
        result = subprocess.run(
            ["git", "checkout", target_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise GitMergeError(f"Failed to checkout {target_branch}: {result.stderr}")

        # 4. Pull latest from target branch
        logger.info(f"Pulling latest {target_branch}...")
        result = subprocess.run(
            ["git", "pull", "origin", target_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"Git pull failed (may not have remote): {result.stderr}")

        # 5. Merge the branch (squash or regular)
        if squash:
            # Squash merge - all commits become one (like Vibe Kanban!)
            logger.info(f"Squash merging {branch_name} into {target_branch}...")

            # Check if branches have diverged (are there actual changes?)
            diff_check = subprocess.run(
                ["git", "diff", f"{target_branch}...{branch_name}", "--stat"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if not diff_check.stdout.strip():
                logger.info(f"No changes between {target_branch} and {branch_name} - branches are identical")
                # No actual changes, but this is considered success
                # Skip the merge since branches are already in sync
                merge_commit = None  # No new commit created
            else:
                logger.info(f"Changes detected:\n{diff_check.stdout}")

                # Stage all changes from branch
                result = subprocess.run(
                    ["git", "merge", "--squash", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                        raise GitMergeError(f"Merge conflict during squash: {result.stderr}")
                    raise GitMergeError(f"Squash merge failed: {result.stderr}")

                # Check if there are changes to commit
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if not status_result.stdout.strip():
                    # No changes to commit - this shouldn't happen after squash
                    logger.warning("No changes staged after squash merge - unexpected state")
                else:
                    # Create single commit
                    result = subprocess.run(
                        ["git", "commit", "-m", f"Merge {branch_name} into {target_branch}"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode != 0:
                        # Log both stdout and stderr for debugging
                        logger.error(f"Git commit failed. Stdout: {result.stdout}, Stderr: {result.stderr}")
                        raise GitMergeError(
                            f"Commit after squash failed: {result.stderr}\n"
                            f"Stdout: {result.stdout}\n"
                            f"This might be due to git user config not being set."
                        )

            logger.info("Squash merge successful")
        else:
            # Regular merge with --no-ff
            logger.info(f"Merging {branch_name} into {target_branch}...")
            result = subprocess.run(
                ["git", "merge", "--no-ff", branch_name, "-m", f"Merge {branch_name} into {target_branch}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                # Check if it's a conflict
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    raise GitMergeError(f"Merge conflict: {result.stderr}")
                raise GitMergeError(f"Merge failed: {result.stderr}")

            logger.info("Merge successful")

        # 6. Get merge commit hash (only if we didn't already set it)
        if 'merge_commit' not in locals():
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            merge_commit = result.stdout.strip() if result.returncode == 0 else None

        # 7. Push to remote (if requested)
        if push_to_remote:
            logger.info(f"Pushing {target_branch} to remote...")
            result = subprocess.run(
                ["git", "push", "origin", target_branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(f"Push failed: {result.stderr}")
                # Don't fail the merge if push fails

        # 8. Delete branch (if requested)
        if delete_branch_after:
            logger.info(f"Deleting branch {branch_name}...")
            result = subprocess.run(
                ["git", "branch", "-d", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                # Try force delete
                result = subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to delete branch: {result.stderr}")

        # Prepare success message based on whether changes were merged
        if merge_commit:
            message = f"Successfully merged {branch_name} into {target_branch}"
        else:
            message = f"Branches {branch_name} and {target_branch} are already in sync (no changes to merge)"

        return SimpleMergeResult(
            success=True,
            message=message,
            merged_branch=branch_name,
            target_branch=target_branch,
            merge_commit=merge_commit,
        )

    except subprocess.TimeoutExpired as e:
        raise GitMergeError(f"Git operation timed out: {e}")
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        raise GitMergeError(str(e))


def cleanup_worktree(repo_path: Path, worktree_path: Path) -> bool:
    """Remove a git worktree directory.

    Args:
        repo_path: Path to the main git repository
        worktree_path: Path to the worktree to remove

    Returns:
        True if cleanup succeeded, False otherwise
    """
    logger.info(f"Cleaning up worktree: {worktree_path}")

    try:
        # Remove worktree using git
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"Git worktree remove failed: {result.stderr}")
            # Try to remove directory manually
            import shutil
            if worktree_path.exists():
                shutil.rmtree(worktree_path)
                logger.info("Manually removed worktree directory")

        # Prune stale worktree references
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )

        logger.info("Worktree cleanup complete")
        return True

    except Exception as e:
        logger.error(f"Worktree cleanup failed: {e}")
        return False
