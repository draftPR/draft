"""Service for reading and parsing smartkanban.yaml configuration."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ExecuteConfig:
    """Configuration for execute jobs.

    YOLO Mode:
        When yolo_mode is enabled, the executor CLI runs with --dangerously-skip-permissions.
        This is ONLY safe when:
        - Execution is isolated in a worktree (enforced by the worker)
        - The repo is in a trusted allowlist (checked if allowlist is non-empty)
        - No secrets are exposed to the executor

        Default is False (permissioned mode) for safety.
    """

    timeout: int = 600  # seconds (default 10 minutes)
    preferred_executor: str = "claude"  # "claude" (headless) or "cursor" (interactive)
    yolo_mode: bool = False  # DANGEROUS: skip permissions prompts (opt-in only)
    yolo_allowlist: list[str] | None = None  # repos where YOLO is allowed (empty = any)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecuteConfig":
        """Create a config instance from a dictionary."""
        return cls(
            timeout=data.get("timeout", 600),
            preferred_executor=data.get("preferred_executor", "claude"),
            yolo_mode=data.get("yolo_mode", False),
            yolo_allowlist=data.get("yolo_allowlist"),
        )

    def is_yolo_allowed(self, repo_path: str) -> bool:
        """Check if YOLO mode is allowed for this repo.

        YOLO mode is allowed if:
        1. yolo_mode is enabled in config
        2. Either yolo_allowlist is empty/None (allow any) OR repo_path is in the list

        Args:
            repo_path: Absolute path to the repository

        Returns:
            True if YOLO mode should be used
        """
        if not self.yolo_mode:
            return False

        # If allowlist is empty or not set, allow any repo
        if not self.yolo_allowlist:
            return True

        # Check if repo is in allowlist
        return repo_path in self.yolo_allowlist


@dataclass
class SmartKanbanConfig:
    """Configuration for Smart Kanban verification."""

    verify_commands: list[str] = field(default_factory=list)
    auto_transition_on_success: bool = False
    execute_config: ExecuteConfig = field(default_factory=ExecuteConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SmartKanbanConfig":
        """Create a config instance from a dictionary."""
        execute_data = data.get("execute_config", {})
        return cls(
            verify_commands=data.get("verify_commands", []),
            auto_transition_on_success=data.get("auto_transition_on_success", False),
            execute_config=ExecuteConfig.from_dict(execute_data) if execute_data else ExecuteConfig(),
        )


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

    def get_verify_commands(self) -> list[str]:
        """Get the list of verification commands."""
        return self.load_config().verify_commands

    def get_auto_transition_on_success(self) -> bool:
        """Get whether to auto-transition to done on success."""
        return self.load_config().auto_transition_on_success

    def get_execute_config(self) -> ExecuteConfig:
        """Get the execute configuration."""
        return self.load_config().execute_config

    def get_execute_timeout(self) -> int:
        """Get the execute job timeout in seconds."""
        return self.load_config().execute_config.timeout

    def get_preferred_executor(self) -> str:
        """Get the preferred executor CLI (cursor or claude)."""
        return self.load_config().execute_config.preferred_executor

