"""Service for discovering and managing git repositories."""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import git
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repo import Repo


@dataclass
class DiscoveredRepo:
    """Represents a discovered git repository."""

    path: str
    name: str
    display_name: str
    default_branch: str | None = None
    remote_url: str | None = None
    is_valid: bool = True
    error_message: str | None = None


@dataclass
class RepoValidation:
    """Result of repository path validation."""

    is_valid: bool
    path: str
    error_message: str | None = None
    metadata: DiscoveredRepo | None = None


class RepoDiscoveryService:
    """Service to discover and register git repositories."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Patterns to exclude from discovery
    EXCLUDE_PATTERNS = {
        "node_modules",
        ".git",
        "vendor",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "target",  # Rust
        ".gradle",  # Gradle
        ".mvn",  # Maven
    }

    async def discover_repos(
        self,
        search_paths: list[str],
        max_depth: int = 3,
        exclude_patterns: set[str] | None = None,
    ) -> list[DiscoveredRepo]:
        """
        Scan directories for git repositories.

        Args:
            search_paths: List of directories to scan
            max_depth: How deep to recurse (default 3)
            exclude_patterns: Additional patterns to exclude

        Returns:
            List of discovered git repositories
        """
        if exclude_patterns is None:
            exclude_patterns = self.EXCLUDE_PATTERNS.copy()
        else:
            exclude_patterns = self.EXCLUDE_PATTERNS | exclude_patterns

        discovered = []

        for search_path in search_paths:
            # Expand user path (~)
            expanded_path = os.path.expanduser(search_path)
            path_obj = Path(expanded_path).resolve()

            if not path_obj.exists():
                continue

            # Walk directory tree
            for root, dirs, _ in os.walk(path_obj, topdown=True):
                # Calculate current depth
                rel_path = Path(root).relative_to(path_obj)
                depth = len(rel_path.parts) if rel_path != Path(".") else 0

                # Prune search if too deep
                if depth >= max_depth:
                    dirs.clear()
                    continue

                # Prune excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_patterns]

                # Check if this directory is a git repo
                git_dir = Path(root) / ".git"
                if git_dir.exists():
                    # Found a git repo
                    repo_path = str(Path(root).resolve())
                    validation = self._validate_repo_path_sync(repo_path)

                    if validation.is_valid and validation.metadata:
                        discovered.append(validation.metadata)

                    # Don't recurse into git repos (avoid submodules)
                    dirs.clear()

        return discovered

    async def validate_repo_path(self, path: str) -> RepoValidation:
        """
        Validate a path is a valid git repository.

        Returns:
            RepoValidation with is_valid, error_message, and metadata
        """
        return self._validate_repo_path_sync(path)

    def _validate_repo_path_sync(self, path: str) -> RepoValidation:
        """Synchronous version of validate_repo_path (for use in discover_repos)."""
        try:
            # Expand and resolve path
            expanded = os.path.expanduser(path)
            path_obj = Path(expanded).resolve()

            # Check if path exists
            if not path_obj.exists():
                return RepoValidation(
                    is_valid=False,
                    path=str(path_obj),
                    error_message=f"Path does not exist: {path_obj}",
                )

            # Check if it's a directory
            if not path_obj.is_dir():
                return RepoValidation(
                    is_valid=False,
                    path=str(path_obj),
                    error_message=f"Path is not a directory: {path_obj}",
                )

            # Try to open as git repo
            try:
                repo = git.Repo(str(path_obj))
            except git.InvalidGitRepositoryError:
                return RepoValidation(
                    is_valid=False,
                    path=str(path_obj),
                    error_message=f"Path is not a git repository: {path_obj}",
                )

            # Extract metadata
            name = path_obj.name
            display_name = name

            # Get default branch
            try:
                default_branch = repo.active_branch.name
            except Exception:
                # Detached HEAD or other issue
                default_branch = "main"

            # Get remote URL
            remote_url = None
            try:
                if repo.remotes:
                    remote_url = repo.remotes.origin.url
            except Exception:
                pass

            metadata = DiscoveredRepo(
                path=str(path_obj),
                name=name,
                display_name=display_name,
                default_branch=default_branch,
                remote_url=remote_url,
                is_valid=True,
            )

            return RepoValidation(
                is_valid=True,
                path=str(path_obj),
                metadata=metadata,
            )

        except Exception as e:
            return RepoValidation(
                is_valid=False,
                path=path,
                error_message=f"Validation error: {str(e)}",
            )

    async def register_repo(
        self,
        path: str,
        display_name: str | None = None,
        setup_script: str | None = None,
        cleanup_script: str | None = None,
        dev_server_script: str | None = None,
    ) -> Repo:
        """
        Register a repository in the global registry.

        Args:
            path: Filesystem path to git repository
            display_name: Optional user-friendly name
            setup_script: Optional setup script
            cleanup_script: Optional cleanup script
            dev_server_script: Optional dev server script

        Returns:
            Created Repo model

        Raises:
            ValueError: If path is invalid or repo already exists
        """
        # Validate path
        validation = await self.validate_repo_path(path)
        if not validation.is_valid:
            raise ValueError(validation.error_message or "Invalid repository path")

        if not validation.metadata:
            raise ValueError("Repository validation returned no metadata")

        # Check if repo already exists
        result = await self.db.execute(
            select(Repo).where(Repo.path == validation.path)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Repository already registered: {validation.path}")

        # Create repo
        metadata = validation.metadata
        repo = Repo(
            id=str(uuid.uuid4()),
            path=validation.path,
            name=metadata.name,
            display_name=display_name or metadata.display_name,
            setup_script=setup_script,
            cleanup_script=cleanup_script,
            dev_server_script=dev_server_script,
            default_branch=metadata.default_branch,
            remote_url=metadata.remote_url,
        )

        self.db.add(repo)
        await self.db.commit()
        await self.db.refresh(repo)

        return repo

    async def get_repo_by_id(self, repo_id: str) -> Repo | None:
        """Get a repo by its ID."""
        result = await self.db.execute(select(Repo).where(Repo.id == repo_id))
        return result.scalar_one_or_none()

    async def get_repo_by_path(self, path: str) -> Repo | None:
        """Get a repo by its path."""
        # Normalize path
        expanded = os.path.expanduser(path)
        normalized = str(Path(expanded).resolve())

        result = await self.db.execute(select(Repo).where(Repo.path == normalized))
        return result.scalar_one_or_none()

    async def get_all_repos(self) -> list[Repo]:
        """Get all registered repos."""
        result = await self.db.execute(select(Repo).order_by(Repo.created_at.desc()))
        return list(result.scalars().all())

    async def update_repo(
        self,
        repo_id: str,
        display_name: str | None = None,
        setup_script: str | None = None,
        cleanup_script: str | None = None,
        dev_server_script: str | None = None,
    ) -> Repo:
        """Update a repo's configuration."""
        repo = await self.get_repo_by_id(repo_id)
        if not repo:
            raise ValueError(f"Repo not found: {repo_id}")

        if display_name is not None:
            repo.display_name = display_name
        if setup_script is not None:
            repo.setup_script = setup_script
        if cleanup_script is not None:
            repo.cleanup_script = cleanup_script
        if dev_server_script is not None:
            repo.dev_server_script = dev_server_script

        await self.db.commit()
        await self.db.refresh(repo)

        return repo

    async def delete_repo(self, repo_id: str) -> None:
        """Delete a repo from the registry."""
        repo = await self.get_repo_by_id(repo_id)
        if not repo:
            raise ValueError(f"Repo not found: {repo_id}")

        await self.db.delete(repo)
        await self.db.commit()
