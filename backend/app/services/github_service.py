"""Service for GitHub integration via GitHub CLI."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.exceptions import ConfigurationError


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""

    number: int
    url: str
    title: str
    state: str  # 'OPEN', 'CLOSED', 'MERGED'
    head_branch: str
    base_branch: str
    merged: bool = False


class GitHubService:
    """Service for interacting with GitHub via CLI."""

    def __init__(self):
        self._gh_path: str | None = None
        self._authenticated: bool | None = None

    @property
    def gh_path(self) -> str:
        """Get path to gh CLI executable."""
        if self._gh_path is None:
            self._gh_path = shutil.which("gh")
            if not self._gh_path:
                raise ConfigurationError(
                    "GitHub CLI (gh) not found. Install from https://cli.github.com/"
                )
        return self._gh_path

    def is_available(self) -> bool:
        """Check if GitHub CLI is available."""
        try:
            return bool(shutil.which("gh"))
        except Exception:
            return False

    async def is_authenticated(self) -> bool:
        """Check if user is authenticated with GitHub CLI."""
        if self._authenticated is not None:
            return self._authenticated

        try:
            result = subprocess.run(
                [self.gh_path, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # gh auth status returns 0 if authenticated
            self._authenticated = result.returncode == 0
            return self._authenticated
        except Exception:
            self._authenticated = False
            return False

    async def ensure_authenticated(self):
        """Ensure user is authenticated, raise if not."""
        if not await self.is_authenticated():
            raise ConfigurationError(
                "Not authenticated with GitHub. Run 'gh auth login' first."
            )

    async def create_pr(
        self,
        repo_path: Path,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> PullRequest:
        """
        Create a pull request.

        Args:
            repo_path: Path to the git repository
            title: PR title
            body: PR description
            head_branch: Source branch (feature branch)
            base_branch: Target branch (e.g., 'main')

        Returns:
            PullRequest object with PR details

        Raises:
            ConfigurationError: If gh CLI not available or not authenticated
            RuntimeError: If PR creation fails
        """
        await self.ensure_authenticated()

        # Build gh pr create command
        cmd = [
            self.gh_path,
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base_branch,
            "--head",
            head_branch,
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                raise RuntimeError(f"Failed to create PR: {error_msg}")

            # Parse PR URL from output
            pr_url = result.stdout.strip()

            # Extract PR number from URL
            # Example: https://github.com/owner/repo/pull/123
            import re

            pr_number_match = re.search(r"/pull/(\d+)", pr_url)
            if not pr_number_match:
                raise RuntimeError(f"Could not extract PR number from URL: {pr_url}")

            pr_number = int(pr_number_match.group(1))

            return PullRequest(
                number=pr_number,
                url=pr_url,
                title=title,
                state="OPEN",
                head_branch=head_branch,
                base_branch=base_branch,
                merged=False,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("PR creation timed out after 30 seconds")
        except Exception as e:
            raise RuntimeError(f"Failed to create PR: {e}")

    async def get_pr_status(self, repo_path: Path, pr_number: int) -> str:
        """
        Get the status of a pull request.

        Args:
            repo_path: Path to the git repository
            pr_number: PR number

        Returns:
            Status string: 'OPEN', 'CLOSED', 'MERGED'
        """
        await self.ensure_authenticated()

        cmd = [
            self.gh_path,
            "pr",
            "view",
            str(pr_number),
            "--json",
            "state",
            "--jq",
            ".state",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to get PR status: {result.stderr}")

            return result.stdout.strip()

        except Exception as e:
            raise RuntimeError(f"Failed to get PR status: {e}")

    async def get_pr_details(self, repo_path: Path, pr_number: int) -> dict[str, any]:
        """
        Get detailed information about a PR.

        Returns:
            Dict with keys: number, title, state, url, headRefName, baseRefName, merged
        """
        await self.ensure_authenticated()

        cmd = [
            self.gh_path,
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,state,url,headRefName,baseRefName,merged",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to get PR details: {result.stderr}")

            return json.loads(result.stdout)

        except Exception as e:
            raise RuntimeError(f"Failed to get PR details: {e}")


# Singleton instance
_github_service: GitHubService | None = None


def get_github_service() -> GitHubService:
    """Get or create GitHubService singleton."""
    global _github_service
    if _github_service is None:
        _github_service = GitHubService()
    return _github_service
