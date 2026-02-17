"""Factory for creating git host providers with auto-detection."""

import logging
import subprocess
from pathlib import Path

from app.services.git_host.github import GitHubProvider
from app.services.git_host.gitlab import GitLabProvider
from app.services.git_host.protocol import GitHostProvider

logger = logging.getLogger(__name__)

# Cached providers by repo path
_providers: dict[str, GitHostProvider] = {}


def detect_git_host(repo_path: Path | None = None) -> str:
    """Detect the git host from the remote URL.

    Args:
        repo_path: Path to a git repository. If None, uses cwd.

    Returns:
        'github', 'gitlab', or 'unknown'
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path or ".",
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return "unknown"

        url = result.stdout.strip().lower()

        if "github.com" in url or "github" in url:
            return "github"
        elif "gitlab.com" in url or "gitlab" in url:
            return "gitlab"
        else:
            return "unknown"

    except Exception as e:
        logger.debug(f"Failed to detect git host: {e}")
        return "unknown"


def get_git_host_provider(
    repo_path: Path | None = None,
    force_provider: str | None = None,
) -> GitHostProvider:
    """Get a git host provider, auto-detecting from the remote URL.

    Args:
        repo_path: Path to a git repository for detection.
        force_provider: Force a specific provider ('github' or 'gitlab').

    Returns:
        A GitHostProvider instance.

    Raises:
        ValueError: If the host cannot be determined or is unsupported.
    """
    cache_key = force_provider or str(repo_path or "default")

    if cache_key in _providers:
        return _providers[cache_key]

    host = force_provider or detect_git_host(repo_path)

    if host == "github":
        provider = GitHubProvider()
    elif host == "gitlab":
        provider = GitLabProvider()
    else:
        # Default to GitHub (most common) but log a warning
        logger.warning(
            f"Could not detect git host (got '{host}'), defaulting to GitHub. "
            "Set force_provider='gitlab' if using GitLab."
        )
        provider = GitHubProvider()

    _providers[cache_key] = provider
    return provider
