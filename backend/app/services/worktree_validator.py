"""Worktree validation service - enforces safety checks for execution.

This module provides hard validation that execution only happens in
properly isolated worktrees, not the main repository.
"""

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class WorktreeValidationError(StrEnum):
    """Types of worktree validation failures."""

    NOT_IN_SMARTKANBAN_DIR = "not_in_smartkanban_dir"
    ON_PROTECTED_BRANCH = "on_protected_branch"
    IS_MAIN_REPO = "is_main_repo"
    NOT_A_GIT_REPO = "not_a_git_repo"
    PATH_MISMATCH = "path_mismatch"


@dataclass
class WorktreeValidationResult:
    """Result of worktree validation."""

    valid: bool
    error: WorktreeValidationError | None = None
    message: str | None = None
    worktree_path: str | None = None
    branch: str | None = None
    main_repo_path: str | None = None

    @classmethod
    def success(cls, worktree_path: str, branch: str) -> "WorktreeValidationResult":
        """Create a successful validation result."""
        return cls(valid=True, worktree_path=worktree_path, branch=branch)

    @classmethod
    def failure(
        cls,
        error: WorktreeValidationError,
        message: str,
        worktree_path: str | None = None,
        branch: str | None = None,
        main_repo_path: str | None = None,
    ) -> "WorktreeValidationResult":
        """Create a failed validation result."""
        return cls(
            valid=False,
            error=error,
            message=message,
            worktree_path=worktree_path,
            branch=branch,
            main_repo_path=main_repo_path,
        )


class WorktreeValidator:
    """Validates that a path is a safe, isolated worktree for execution.

    Safety Checks:
    1. Path must be under .smartkanban/worktrees/
    2. Branch must NOT be main/master/develop (protected branches)
    3. git rev-parse --show-toplevel must match the worktree path
    4. Worktree path must be different from the main repo path

    These checks prevent accidental execution in the main repository.
    """

    # Protected branches that should never be modified by automated execution
    PROTECTED_BRANCHES = {"main", "master", "develop", "production", "staging"}

    # Required path component for worktrees
    WORKTREE_PATH_MARKER = ".smartkanban/worktrees"

    def __init__(self, main_repo_path: Path | str):
        """
        Initialize the validator.

        Args:
            main_repo_path: Path to the main repository (not a worktree).
        """
        self.main_repo_path = Path(main_repo_path).resolve()

    def validate(self, worktree_path: Path | str) -> WorktreeValidationResult:
        """
        Validate that a path is a safe worktree for execution.

        Args:
            worktree_path: Path to validate as a worktree.

        Returns:
            WorktreeValidationResult with validation status and details.
        """
        worktree = Path(worktree_path).resolve()
        worktree_str = str(worktree)

        # Check 1: Path must be under .smartkanban/worktrees/
        if self.WORKTREE_PATH_MARKER not in worktree_str:
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.NOT_IN_SMARTKANBAN_DIR,
                message=(
                    f"Worktree path must be under {self.WORKTREE_PATH_MARKER}/. "
                    f"Got: {worktree_str}"
                ),
                worktree_path=worktree_str,
            )

        # Check 2: Must be a git repository
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return WorktreeValidationResult.failure(
                    error=WorktreeValidationError.NOT_A_GIT_REPO,
                    message=f"Not a git repository: {worktree_str}",
                    worktree_path=worktree_str,
                )
            git_toplevel = Path(result.stdout.strip()).resolve()
        except subprocess.TimeoutExpired:
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.NOT_A_GIT_REPO,
                message="git rev-parse timed out",
                worktree_path=worktree_str,
            )
        except Exception as e:
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.NOT_A_GIT_REPO,
                message=f"Failed to check git status: {e}",
                worktree_path=worktree_str,
            )

        # Check 3: git toplevel must match worktree path (or be under it)
        # This catches cases where someone symlinks or mounts a worktree elsewhere
        if git_toplevel != worktree and not str(git_toplevel).startswith(str(worktree)):
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.PATH_MISMATCH,
                message=(
                    f"Git toplevel doesn't match worktree path. "
                    f"Toplevel: {git_toplevel}, Worktree: {worktree}"
                ),
                worktree_path=worktree_str,
            )

        # Check 4: Worktree must NOT be the main repo
        if git_toplevel == self.main_repo_path:
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.IS_MAIN_REPO,
                message=(
                    f"Cannot execute in main repository. "
                    f"Use a worktree under {self.WORKTREE_PATH_MARKER}/. "
                    f"Main repo: {self.main_repo_path}"
                ),
                worktree_path=worktree_str,
                main_repo_path=str(self.main_repo_path),
            )

        # Check 5: Get current branch and verify it's not protected
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if branch_result.returncode != 0:
                branch = "unknown"
            else:
                branch = branch_result.stdout.strip()
        except Exception:
            branch = "unknown"

        if branch.lower() in self.PROTECTED_BRANCHES:
            return WorktreeValidationResult.failure(
                error=WorktreeValidationError.ON_PROTECTED_BRANCH,
                message=(
                    f"Cannot execute on protected branch '{branch}'. "
                    f"Protected branches: {', '.join(sorted(self.PROTECTED_BRANCHES))}"
                ),
                worktree_path=worktree_str,
                branch=branch,
            )

        # All checks passed
        return WorktreeValidationResult.success(
            worktree_path=worktree_str,
            branch=branch,
        )

    def is_safe_for_execution(self, worktree_path: Path | str) -> bool:
        """
        Quick check if a path is safe for execution.

        Args:
            worktree_path: Path to check.

        Returns:
            True if the path passes all safety checks.
        """
        return self.validate(worktree_path).valid
