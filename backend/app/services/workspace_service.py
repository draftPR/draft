"""Service layer for Workspace operations with git worktree management."""

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_dir import get_logs_dir, get_worktree_dir, get_worktrees_root
from app.exceptions import (
    BranchNotFoundError,
    NotAGitRepositoryError,
    ResourceNotFoundError,
    WorktreeCreationError,
)
from app.models.board import Board
from app.models.ticket import Ticket
from app.models.workspace import Workspace

# Default workspace root (parent of backend directory)
DEFAULT_REPO_PATH = Path(__file__).parent.parent.parent.parent


class WorkspaceService:
    """Service class for Workspace business logic and git worktree management."""

    def __init__(self, db: Session):
        """Initialize with a database session (sync or async compatible)."""
        self.db = db

    @staticmethod
    def get_repo_path() -> Path:
        """
        Get the git repository path from environment or default.

        Returns:
            Path to the git repository root.
        """
        repo_path = os.getenv("GIT_REPO_PATH")
        if repo_path:
            return Path(repo_path)
        return DEFAULT_REPO_PATH

    @staticmethod
    def get_base_branch() -> str:
        """
        Get the base branch name from environment or default.

        Returns:
            The base branch name (defaults to 'main').
        """
        return os.getenv("BASE_BRANCH", "main")

    @classmethod
    def ensure_repo_is_git(cls) -> Path:
        """
        Validate that the configured repo path is a git repository.

        Returns:
            The validated repo path.

        Raises:
            NotAGitRepositoryError: If the path is not a git repository.
        """
        repo_path = cls.get_repo_path()
        git_dir = repo_path / ".git"

        if not git_dir.exists():
            raise NotAGitRepositoryError(str(repo_path))

        return repo_path

    @classmethod
    def _run_git_command(
        cls,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command using subprocess.

        Args:
            args: Git command arguments (without 'git' prefix).
            cwd: Working directory for the command.
            check: Whether to raise on non-zero exit code.

        Returns:
            CompletedProcess with stdout/stderr.

        Raises:
            WorktreeCreationError: If the command fails and check=True.
        """
        cmd = ["git"] + args
        cwd = cwd or cls.get_repo_path()

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise WorktreeCreationError(
                f"Git command failed: {' '.join(cmd)}",
                git_error=e.stderr.strip() if e.stderr else str(e),
            )

    @classmethod
    def _validate_base_branch(cls, repo_path: Path) -> str:
        """
        Validate that the base branch exists, falling back to 'master' if needed.

        Args:
            repo_path: Path to the git repository.

        Returns:
            The validated base branch name.

        Raises:
            BranchNotFoundError: If neither main nor master branch exists.
        """
        base_branch = cls.get_base_branch()

        # Check if the base branch exists
        result = cls._run_git_command(
            ["rev-parse", "--verify", f"refs/heads/{base_branch}"],
            cwd=repo_path,
            check=False,
        )

        if result.returncode == 0:
            return base_branch

        # If configured branch doesn't exist, try fallback to 'master'
        if base_branch != "master":
            result = cls._run_git_command(
                ["rev-parse", "--verify", "refs/heads/master"],
                cwd=repo_path,
                check=False,
            )
            if result.returncode == 0:
                return "master"

        raise BranchNotFoundError(base_branch)

    @classmethod
    def _get_worktree_dir(cls, ticket_id: str, board_id: str | None = None) -> Path:
        """
        Get the worktree directory path for a ticket.

        Uses central data dir: ~/.draft/worktrees/{board_id}/{ticket_id}/

        Args:
            ticket_id: The ticket UUID.
            board_id: The board UUID (used for directory grouping).

        Returns:
            Path to the worktree directory.
        """
        return get_worktree_dir(board_id or "default", ticket_id)

    @classmethod
    def _get_branch_name(cls, goal_id: str, ticket_id: str) -> str:
        """
        Generate the branch name for a ticket.

        Args:
            goal_id: The goal UUID.
            ticket_id: The ticket UUID.

        Returns:
            Branch name in format: goal/{goal_id}/ticket/{ticket_id}
        """
        return f"goal/{goal_id}/ticket/{ticket_id}"

    def get_workspace_by_ticket_id(self, ticket_id: str) -> Workspace | None:
        """
        Get workspace for a ticket.

        Args:
            ticket_id: The ticket UUID.

        Returns:
            Workspace if exists, None otherwise.
        """
        result = self.db.execute(
            select(Workspace).where(Workspace.ticket_id == ticket_id)
        )
        return result.scalar_one_or_none()

    def get_worktree_path(self, ticket_id: str) -> Path | None:
        """
        Get the worktree path for a ticket from the database.

        Args:
            ticket_id: The ticket UUID.

        Returns:
            Path to the worktree directory, or None if not found or cleaned up.
        """
        workspace = self.get_workspace_by_ticket_id(ticket_id)
        if workspace and workspace.is_active:
            return Path(workspace.worktree_path)
        return None

    def create_worktree(self, ticket_id: str, goal_id: str) -> Workspace:
        """
        Create a git worktree for a ticket.

        This method:
        1. Validates the repository is a git repo
        2. Validates the base branch exists
        3. Creates a new branch based on the base branch
        4. Creates a worktree at .draft/worktrees/{ticket_id}/
        5. Records the workspace in the database

        Args:
            ticket_id: The ticket UUID.
            goal_id: The goal UUID (for branch naming).

        Returns:
            The created Workspace instance.

        Raises:
            NotAGitRepositoryError: If not a git repository.
            BranchNotFoundError: If base branch doesn't exist.
            WorktreeCreationError: If worktree creation fails.
            ResourceNotFoundError: If the ticket doesn't exist.
        """
        # Check if workspace already exists
        existing = self.get_workspace_by_ticket_id(ticket_id)
        if existing and existing.is_active:
            return existing

        # Verify ticket exists
        result = self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Use board's repo_root if available, otherwise fall back to env/default
        board_repo_root = None
        if ticket.board_id:
            board_result = self.db.execute(
                select(Board).where(Board.id == ticket.board_id)
            )
            board = board_result.scalar_one_or_none()
            if board and board.repo_root:
                board_repo_root = Path(board.repo_root)

        # Validate git repo
        if board_repo_root:
            git_dir = board_repo_root / ".git"
            if not git_dir.exists():
                raise NotAGitRepositoryError(str(board_repo_root))
            repo_path = board_repo_root
        else:
            repo_path = self.ensure_repo_is_git()

        # Validate base branch
        base_branch = self._validate_base_branch(repo_path)

        # Generate paths and names
        worktree_dir = self._get_worktree_dir(ticket_id, board_id=ticket.board_id)
        branch_name = self._get_branch_name(goal_id, ticket_id)

        # Create parent directories
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing worktree directory if it exists (from a previous failed attempt)
        if worktree_dir.exists():
            # Security: reject symlinks to prevent directory traversal attacks
            if worktree_dir.is_symlink():
                raise WorktreeCreationError(
                    f"Worktree path is a symlink (potential security issue): {worktree_dir}",
                    git_error="symlink_detected",
                )
            # Security: ensure resolved path stays within the central data dir
            resolved = worktree_dir.resolve()
            worktrees_root = get_worktrees_root().resolve()
            if not str(resolved).startswith(str(worktrees_root) + os.sep):
                raise WorktreeCreationError(
                    f"Worktree path escapes data dir boundary: {resolved}",
                    git_error="path_traversal_detected",
                )
            shutil.rmtree(worktree_dir)

        # Check if branch already exists (e.g., from previous execution before cleanup)
        branch_exists_result = self._run_git_command(
            ["rev-parse", "--verify", f"refs/heads/{branch_name}"],
            cwd=repo_path,
            check=False,
        )
        branch_exists = branch_exists_result.returncode == 0

        if branch_exists:
            # Branch exists - create worktree using existing branch
            # First, make sure the branch isn't checked out elsewhere
            self._run_git_command(
                ["worktree", "prune"],
                cwd=repo_path,
                check=False,
            )
            # Create worktree with existing branch
            self._run_git_command(
                ["worktree", "add", str(worktree_dir), branch_name],
                cwd=repo_path,
            )
        else:
            # Create the worktree with a new branch
            self._run_git_command(
                ["worktree", "add", "-b", branch_name, str(worktree_dir), base_branch],
                cwd=repo_path,
            )

        # Create or update workspace record
        if existing:
            # Reactivate existing workspace
            existing.worktree_path = str(worktree_dir)
            existing.branch_name = branch_name
            existing.cleaned_up_at = None
            self.db.flush()
            return existing

        # Create new workspace record
        workspace = Workspace(
            ticket_id=ticket_id,
            board_id=ticket.board_id,
            worktree_path=str(worktree_dir),
            branch_name=branch_name,
        )
        self.db.add(workspace)
        self.db.flush()

        return workspace

    def ensure_workspace(self, ticket_id: str, goal_id: str) -> Workspace:
        """
        Ensure a workspace exists for a ticket, creating one if necessary.

        Args:
            ticket_id: The ticket UUID.
            goal_id: The goal UUID.

        Returns:
            The existing or newly created Workspace.
        """
        workspace = self.get_workspace_by_ticket_id(ticket_id)
        if workspace and workspace.is_active:
            # Verify the worktree directory still exists
            worktree_path = Path(workspace.worktree_path)
            if worktree_path.exists():
                # Verify the worktree belongs to the board's repo (not a stale worktree
                # from a different repo, e.g. after GIT_REPO_PATH was changed).
                if self._worktree_matches_board_repo(worktree_path, workspace.board_id):
                    return workspace
                # Wrong repo — force cleanup and recreate
                import logging

                logging.getLogger(__name__).warning(
                    f"Worktree {worktree_path} belongs to wrong repo; recreating."
                )
                workspace.cleaned_up_at = datetime.now(UTC)
                self.db.flush()
            else:
                # Worktree was deleted externally, recreate it
                workspace.cleaned_up_at = datetime.now(UTC)
                self.db.flush()

        return self.create_worktree(ticket_id, goal_id)

    def _worktree_matches_board_repo(
        self, worktree_path: Path, board_id: str | None
    ) -> bool:
        """Check that an existing worktree belongs to the board's repo_root."""
        if not board_id:
            return True  # No board — can't verify, assume OK
        board_result = self.db.execute(select(Board).where(Board.id == board_id))
        board = board_result.scalar_one_or_none()
        if not board or not board.repo_root:
            return True  # No repo_root configured — assume OK
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False
            common_dir = Path(result.stdout.strip()).resolve()
            board_git_dir = (Path(board.repo_root) / ".git").resolve()
            return str(common_dir).startswith(str(board_git_dir))
        except Exception:
            return True  # Can't verify, assume OK

    def cleanup_worktree(self, ticket_id: str) -> bool:
        """
        Remove a worktree and mark it as cleaned up.

        Args:
            ticket_id: The ticket UUID.

        Returns:
            True if cleanup was performed, False if no active workspace found.
        """
        workspace = self.get_workspace_by_ticket_id(ticket_id)
        if not workspace or not workspace.is_active:
            return False

        # Use board's repo_root if available
        repo_path = self.get_repo_path()
        if workspace.board_id:
            board_result = self.db.execute(
                select(Board).where(Board.id == workspace.board_id)
            )
            board = board_result.scalar_one_or_none()
            if board and board.repo_root:
                repo_path = Path(board.repo_root)
        worktree_dir = Path(workspace.worktree_path)

        # Remove the worktree using git
        if worktree_dir.exists():
            self._run_git_command(
                ["worktree", "remove", "--force", str(worktree_dir)],
                cwd=repo_path,
                check=False,  # Don't fail if already removed
            )

        # Delete the branch
        self._run_git_command(
            ["branch", "-D", workspace.branch_name],
            cwd=repo_path,
            check=False,  # Don't fail if branch doesn't exist
        )

        # Mark as cleaned up
        workspace.cleaned_up_at = datetime.now(UTC)
        self.db.flush()

        return True

    def get_logs_dir(self, ticket_id: str) -> Path | None:
        """
        Get the central logs directory.

        Args:
            ticket_id: The ticket UUID (unused, kept for API compat).

        Returns:
            Path to the central logs directory, or None if no active workspace.
        """
        worktree_path = self.get_worktree_path(ticket_id)
        if worktree_path is None:
            return None

        return get_logs_dir()
