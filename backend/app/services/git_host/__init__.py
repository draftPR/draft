"""Git host abstraction layer for GitHub and GitLab."""

from app.services.git_host.factory import detect_git_host, get_git_host_provider
from app.services.git_host.protocol import GitHostProvider, PullRequest

__all__ = [
    "GitHostProvider",
    "PullRequest",
    "get_git_host_provider",
    "detect_git_host",
]
