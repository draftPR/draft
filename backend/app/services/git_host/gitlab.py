"""GitLab provider implementation using glab CLI."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from app.exceptions import ConfigurationError
from app.services.git_host.protocol import PullRequest


class GitLabProvider:
    """GitLab provider using the glab CLI."""

    def __init__(self) -> None:
        self._glab_path: str | None = None
        self._authenticated: bool | None = None

    @property
    def name(self) -> str:
        return "gitlab"

    @property
    def glab_path(self) -> str:
        if self._glab_path is None:
            self._glab_path = shutil.which("glab")
            if not self._glab_path:
                raise ConfigurationError(
                    "GitLab CLI (glab) not found. "
                    "Install from https://gitlab.com/gitlab-org/cli"
                )
        return self._glab_path

    def is_available(self) -> bool:
        try:
            return bool(shutil.which("glab"))
        except Exception:
            return False

    async def is_authenticated(self) -> bool:
        if self._authenticated is not None:
            return self._authenticated
        try:
            result = subprocess.run(
                [self.glab_path, "auth", "status"],
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
                "Not authenticated with GitLab. Run 'glab auth login' first."
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
            self.glab_path,
            "mr",
            "create",
            "--title",
            title,
            "--description",
            body,
            "--target-branch",
            base_branch,
            "--source-branch",
            head_branch,
            "--no-editor",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to create MR: {result.stderr.strip()}")

            mr_url = result.stdout.strip()
            # Extract MR number from URL like https://gitlab.com/org/repo/-/merge_requests/123
            mr_number_match = re.search(r"/merge_requests/(\d+)", mr_url)
            if not mr_number_match:
                # Try to find it in any line
                for line in mr_url.split("\n"):
                    mr_number_match = re.search(r"/merge_requests/(\d+)", line)
                    if mr_number_match:
                        mr_url = line.strip()
                        break

            if not mr_number_match:
                raise RuntimeError(f"Could not extract MR number from output: {mr_url}")

            return PullRequest(
                number=int(mr_number_match.group(1)),
                url=mr_url,
                title=title,
                state="OPEN",
                head_branch=head_branch,
                base_branch=base_branch,
                merged=False,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("MR creation timed out after 30 seconds")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to create MR: {e}")

    async def get_pr_status(self, repo_path: Path, pr_number: int) -> str:
        await self.ensure_authenticated()

        cmd = [
            self.glab_path,
            "mr",
            "view",
            str(pr_number),
            "--output",
            "json",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to get MR status: {result.stderr}")

            data = json.loads(result.stdout)
            state = data.get("state", "").upper()
            if state == "MERGED":
                return "MERGED"
            elif state == "CLOSED":
                return "CLOSED"
            return "OPEN"
        except Exception as e:
            raise RuntimeError(f"Failed to get MR status: {e}")

    async def get_pr_details(self, repo_path: Path, pr_number: int) -> dict[str, any]:
        await self.ensure_authenticated()

        cmd = [
            self.glab_path,
            "mr",
            "view",
            str(pr_number),
            "--output",
            "json",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to get MR details: {result.stderr}")

            data = json.loads(result.stdout)
            # Normalize to the same shape as GitHub
            state = data.get("state", "").upper()
            merged = state == "MERGED"
            if not merged and state == "CLOSED":
                pass  # keep as CLOSED
            elif not merged:
                state = "OPEN"

            return {
                "number": data.get("iid", pr_number),
                "title": data.get("title", ""),
                "state": state,
                "url": data.get("web_url", ""),
                "headRefName": data.get("source_branch", ""),
                "baseRefName": data.get("target_branch", ""),
                "merged": merged,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get MR details: {e}")
