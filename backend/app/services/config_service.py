"""Service for reading and parsing smartkanban.yaml configuration."""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class YoloStatus(str, Enum):
    """Result of YOLO mode check."""

    DISABLED = "disabled"  # yolo_mode: false
    ALLOWED = "allowed"  # yolo_mode: true AND repo in allowlist
    REFUSED = "refused"  # yolo_mode: true BUT allowlist empty or repo not in list


@dataclass
class ProjectConfig:
    """Project-level configuration."""

    repo_root: str = "."  # Path to repo root (resolved to absolute at runtime)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        """Create a config instance from a dictionary."""
        return cls(
            repo_root=data.get("repo_root", "."),
        )

    def get_absolute_repo_root(self, config_dir: Path) -> Path:
        """Resolve repo_root to an absolute path relative to config file location."""
        root = Path(self.repo_root)
        if root.is_absolute():
            return root
        return (config_dir / root).resolve()


@dataclass
class ExecuteConfig:
    """Configuration for execute jobs.

    YOLO Mode Safety:
        YOLO mode (--dangerously-skip-permissions) is ONLY allowed when:
        1. yolo_mode: true in config
        2. yolo_allowlist is NON-EMPTY
        3. The worktree path is in the allowlist

        If yolo_mode is true but allowlist is empty, execution REFUSES and
        transitions to needs_human. This prevents accidental YOLO.

        Default is yolo_mode: false (permissioned mode).
    """

    timeout: int = 600  # seconds (default 10 minutes)
    preferred_executor: str = "claude"  # "claude" (headless) or "cursor" (interactive)
    yolo_mode: bool = False  # DANGEROUS: skip permissions prompts (opt-in only)
    yolo_allowlist: list[str] = field(default_factory=list)  # REQUIRED when yolo_mode=true

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecuteConfig":
        """Create a config instance from a dictionary."""
        return cls(
            timeout=data.get("timeout", 600),
            preferred_executor=data.get("preferred_executor", "claude"),
            yolo_mode=data.get("yolo_mode", False),
            yolo_allowlist=data.get("yolo_allowlist") or [],
        )

    def check_yolo_status(self, worktree_path: str, repo_root: str | None = None) -> YoloStatus:
        """Check YOLO mode status for a given worktree.

        Safety Policy:
        - If yolo_mode is False → DISABLED (use permissioned mode)
        - If yolo_mode is True but allowlist is empty → REFUSED (refuse to run)
        - If yolo_mode is True and repo_root in allowlist → ALLOWED
        - If yolo_mode is True but repo_root not in allowlist → REFUSED

        Path Matching:
        - All paths are resolved to absolute canonical paths (symlinks resolved)
        - Allowlist entries can be the repo root OR a parent directory
        - Worktree must be a descendant of an allowlisted path

        Args:
            worktree_path: Path to the worktree
            repo_root: Path to the main repo root (if different from worktree parent)

        Returns:
            YoloStatus indicating whether YOLO mode should be used
        """
        if not self.yolo_mode:
            return YoloStatus.DISABLED

        # CRITICAL: Empty allowlist + yolo_mode=true → REFUSE
        # This prevents "I turned on YOLO and forgot to set allowlist"
        if not self.yolo_allowlist:
            return YoloStatus.REFUSED

        # Resolve to canonical absolute paths (follows symlinks)
        # Use realpath for symlink resolution, then resolve for normalization
        worktree_canonical = os.path.realpath(worktree_path)

        # If repo_root is provided, use it; otherwise derive from worktree path
        # (worktrees are typically under {repo_root}/.smartkanban/worktrees/)
        if repo_root:
            check_path = os.path.realpath(repo_root)
        else:
            check_path = worktree_canonical

        # Check if the path (or repo root) is under any allowlisted path
        for allowed_path in self.yolo_allowlist:
            allowed_canonical = os.path.realpath(allowed_path)

            # Exact match
            if check_path == allowed_canonical:
                return YoloStatus.ALLOWED

            # Check if check_path is a descendant of allowed_canonical
            # Use os.path.commonpath to safely determine ancestry
            try:
                common = os.path.commonpath([check_path, allowed_canonical])
                if common == allowed_canonical:
                    return YoloStatus.ALLOWED
            except ValueError:
                # Different drives on Windows, no common path
                continue

        return YoloStatus.REFUSED

    def get_yolo_refusal_reason(self, repo_root: str | None = None) -> str:
        """Get a human-readable reason for YOLO refusal.

        Args:
            repo_root: The repo root path to include in the message
        """
        if not self.yolo_allowlist:
            return (
                "YOLO mode enabled but yolo_allowlist is empty. "
                "For safety, you must explicitly list trusted repo paths in yolo_allowlist. "
                "Refusing to run with --dangerously-skip-permissions."
            )
        msg = "YOLO mode enabled but this repo is not in yolo_allowlist. "
        if repo_root:
            msg += f"Repo root: {os.path.realpath(repo_root)}. "
        msg += f"Allowlist: {[os.path.realpath(p) for p in self.yolo_allowlist]}. "
        msg += "Add this path to yolo_allowlist if you trust it."
        return msg

    def get_yolo_refusal_reason(self) -> str:
        """Get a human-readable reason for YOLO refusal."""
        if not self.yolo_allowlist:
            return (
                "YOLO mode enabled but yolo_allowlist is empty. "
                "For safety, you must explicitly list trusted repo paths in yolo_allowlist. "
                "Refusing to run with --dangerously-skip-permissions."
            )
        return (
            "YOLO mode enabled but this worktree is not in yolo_allowlist. "
            "Add this path to yolo_allowlist if you trust it."
        )


@dataclass
class VerifyConfig:
    """Configuration for verify jobs."""

    commands: list[str] = field(default_factory=list)
    on_success: str = "needs_human"  # "needs_human" or "done"
    on_failure: str = "blocked"  # "blocked" (only option for now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerifyConfig":
        """Create a config instance from a dictionary."""
        return cls(
            commands=data.get("commands") or [],
            on_success=data.get("on_success", "needs_human"),
            on_failure=data.get("on_failure", "blocked"),
        )


@dataclass
class SmartKanbanConfig:
    """Root configuration for Smart Kanban.

    Structure:
        project:
          repo_root: "."

        execute_config:
          timeout: 600
          preferred_executor: "claude"
          yolo_mode: false
          yolo_allowlist: []

        verify_config:
          commands: [...]
          on_success: "needs_human"
          on_failure: "blocked"

    Legacy Support:
        For backwards compatibility, also supports:
        - verify_commands (top-level) → verify_config.commands
        - auto_transition_on_success → verify_config.on_success
    """

    project: ProjectConfig = field(default_factory=ProjectConfig)
    execute_config: ExecuteConfig = field(default_factory=ExecuteConfig)
    verify_config: VerifyConfig = field(default_factory=VerifyConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SmartKanbanConfig":
        """Create a config instance from a dictionary."""
        # Parse project config
        project_data = data.get("project", {})
        project = ProjectConfig.from_dict(project_data) if project_data else ProjectConfig()

        # Parse execute config
        execute_data = data.get("execute_config", {})
        execute_config = ExecuteConfig.from_dict(execute_data) if execute_data else ExecuteConfig()

        # Parse verify config (with legacy fallbacks)
        verify_data = data.get("verify_config", {})
        if verify_data:
            verify_config = VerifyConfig.from_dict(verify_data)
        else:
            # Legacy support: top-level verify_commands and auto_transition_on_success
            legacy_commands = data.get("verify_commands", [])
            legacy_auto = data.get("auto_transition_on_success", False)
            verify_config = VerifyConfig(
                commands=legacy_commands,
                on_success="done" if legacy_auto else "needs_human",
                on_failure="blocked",
            )

        return cls(
            project=project,
            execute_config=execute_config,
            verify_config=verify_config,
        )

    # Convenience properties for backwards compatibility
    @property
    def verify_commands(self) -> list[str]:
        """Get verification commands (legacy accessor)."""
        return self.verify_config.commands

    @property
    def auto_transition_on_success(self) -> bool:
        """Get auto-transition setting (legacy accessor)."""
        return self.verify_config.on_success == "done"


class ConfigService:
    """Service for reading and parsing smartkanban.yaml configuration."""

    CONFIG_FILENAME = "smartkanban.yaml"
    _cache: dict[str, SmartKanbanConfig] = {}

    def __init__(self, repo_path: Path | str | None = None):
        """
        Initialize the config service.

        Args:
            repo_path: Path to the git repository root.
                      If None, uses GIT_REPO_PATH env var or current directory.
        """
        if repo_path is None:
            repo_path = os.environ.get("GIT_REPO_PATH", ".")
        self.repo_path = Path(repo_path)

    @property
    def config_path(self) -> Path:
        """Get the path to the config file."""
        return self.repo_path / self.CONFIG_FILENAME

    def load_config(self, use_cache: bool = True) -> SmartKanbanConfig:
        """
        Load and parse the smartkanban.yaml configuration.

        Args:
            use_cache: Whether to use cached config if available.

        Returns:
            SmartKanbanConfig instance with parsed configuration.
            Returns default config if file doesn't exist or is invalid.
        """
        cache_key = str(self.config_path)

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        config = self._load_config_from_file()

        if use_cache:
            self._cache[cache_key] = config

        return config

    def _load_config_from_file(self) -> SmartKanbanConfig:
        """Load config from file, returning defaults if not found or invalid."""
        if not self.config_path.exists():
            return SmartKanbanConfig()

        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f)

            if data is None:
                return SmartKanbanConfig()

            if not isinstance(data, dict):
                return SmartKanbanConfig()

            return SmartKanbanConfig.from_dict(data)

        except yaml.YAMLError:
            return SmartKanbanConfig()
        except OSError:
            return SmartKanbanConfig()

    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._cache.clear()

    # Convenience methods
    def get_verify_commands(self) -> list[str]:
        """Get the list of verification commands."""
        return self.load_config().verify_commands

    def get_verify_on_success(self) -> str:
        """Get the target state when verification succeeds."""
        return self.load_config().verify_config.on_success

    def get_execute_config(self) -> ExecuteConfig:
        """Get the execute configuration."""
        return self.load_config().execute_config

    def get_execute_timeout(self) -> int:
        """Get the execute job timeout in seconds."""
        return self.load_config().execute_config.timeout

    def get_preferred_executor(self) -> str:
        """Get the preferred executor CLI (cursor or claude)."""
        return self.load_config().execute_config.preferred_executor

    def get_repo_root(self) -> Path:
        """Get the absolute repo root path."""
        config = self.load_config()
        return config.project.get_absolute_repo_root(self.repo_path)
