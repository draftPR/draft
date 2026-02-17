"""GitHub provider implementation using gh CLI."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from app.exceptions import ConfigurationError
from app.services.git_host.protocol import PullRequest


class GitHubProvider:
    """GitHub provider using the gh CLI."""

    def __init__(self) -> None:
        self._gh_path: str | None = None
        self._authenticated: bool | None = None

    @property
    def name(self) -> str:
        return "github"

    @property
    def gh_path(self) -> str:
        if self._gh_path is None:
            self._gh_path = shutil.which("gh")
            if not self._gh_path:
                raise ConfigurationError(
                    "GitHub CLI (gh) not found. Install from https://cli.github.com/"
                )
        return self._gh_path

    def is_available(self) -> bool:
        try:
            return bool(shutil.which("gh"))
        except Exception:
            return False

    async def is_authenticated(self) -> bool:
        if self._authenticated is not None:
            return self._authenticated
        try:
            result = subprocess.run(
                [self.gh_path, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._authenticated = result.returncode == 0
            return self._authenticated
        except Exception:
            self._authenticated = False
            return False

    async def ensure_authenticated(self) -> None:
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
        await self.ensure_authenticated()

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
                raise RuntimeError(f"Failed to create PR: {result.stderr.strip()}")

            pr_url = result.stdout.strip()
            pr_number_match = re.search(r"/pull/(\d+)", pr_url)
            if not pr_number_match:
                raise RuntimeError(f"Could not extract PR number from URL: {pr_url}")

            return PullRequest(
                number=int(pr_number_match.group(1)),
                url=pr_url,
                title=title,
                state="OPEN",
                head_branch=head_branch,
                base_branch=base_branch,
                merged=False,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("PR creation timed out after 30 seconds")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to create PR: {e}")

    async def get_pr_status(self, repo_path: Path, pr_number: int) -> str:
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
