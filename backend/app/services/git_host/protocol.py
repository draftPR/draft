"""Git host provider protocol definition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class PullRequest:
    """Represents a pull/merge request."""

    number: int
    url: str
    title: str
    state: str  # 'OPEN', 'CLOSED', 'MERGED'
    head_branch: str
    base_branch: str
    merged: bool = False


@runtime_checkable
class GitHostProvider(Protocol):
    """Protocol for git hosting providers (GitHub, GitLab, etc.)."""

    @property
    def name(self) -> str:
        """Provider name (e.g. 'github', 'gitlab')."""
        ...

    def is_available(self) -> bool:
        """Check if the CLI tool for this provider is installed."""
        ...

    async def is_authenticated(self) -> bool:
        """Check if the user is authenticated with this provider."""
        ...

    async def ensure_authenticated(self) -> None:
        """Ensure user is authenticated, raise ConfigurationError if not."""
        ...

    async def create_pr(
        self,
        repo_path: Path,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> PullRequest:
        """Create a pull/merge request."""
        ...

    async def get_pr_status(self, repo_path: Path, pr_number: int) -> str:
        """Get the status of a PR: 'OPEN', 'CLOSED', or 'MERGED'."""
        ...

    async def get_pr_details(self, repo_path: Path, pr_number: int) -> dict[str, any]:
        """Get detailed information about a PR."""
        ...

    async def add_pr_comment(self, repo_path: Path, pr_number: int, body: str) -> dict:
        """Add a comment to a PR."""
        ...

    async def list_pr_comments(self, repo_path: Path, pr_number: int) -> list[dict]:
        """List comments on a PR."""
        ...

    async def merge_pr(
        self, repo_path: Path, pr_number: int, strategy: str = "squash"
    ) -> dict:
        """Merge a PR with the given strategy (squash, merge, rebase)."""
        ...
