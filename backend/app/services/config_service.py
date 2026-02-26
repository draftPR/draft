"""Service for reading and parsing smartkanban.yaml configuration."""

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class YoloStatus(StrEnum):
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
    executor_model: str | None = None  # Optional model override for executor
    max_parallel_jobs: int = 1  # Max concurrent execute jobs (1 = sequential)
    yolo_mode: bool = False  # DANGEROUS: skip permissions prompts (opt-in only)
    yolo_allowlist: list[str] = field(
        default_factory=list
    )  # REQUIRED when yolo_mode=true

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecuteConfig":
        """Create a config instance from a dictionary."""
        return cls(
            timeout=data.get("timeout", 600),
            preferred_executor=data.get("preferred_executor", "claude"),
            executor_model=data.get("executor_model"),
            max_parallel_jobs=max(1, data.get("max_parallel_jobs", 1)),
            yolo_mode=data.get("yolo_mode", False),
            yolo_allowlist=data.get("yolo_allowlist") or [],
        )

    def check_yolo_status(
        self, worktree_path: str, repo_root: str | None = None
    ) -> YoloStatus:
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


@dataclass
class VerifyConfig:
    """Configuration for verify jobs.

    Note: After verification passes, tickets always transition to 'needs_human'
    for user review. Only when the user approves the revision does it move to 'done'.
    The on_success field is kept for backwards compatibility but is ignored.
    """

    commands: list[str] = field(default_factory=list)
    on_success: str = "needs_human"  # DEPRECATED: Always "needs_human", kept for backwards compatibility
    on_failure: str = "blocked"  # "blocked" (only option for now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerifyConfig":
        """Create a config instance from a dictionary."""
        return cls(
            commands=data.get("commands") or [],
            on_success="needs_human",  # Always needs_human - user must approve to move to done
            on_failure=data.get("on_failure", "blocked"),
        )


@dataclass
class CleanupConfig:
    """Configuration for cleanup policy.

    Controls automatic cleanup of worktrees and evidence files.
    """

    auto_cleanup_on_merge: bool = True  # Delete worktree after successful merge
    worktree_ttl_days: int = 14  # Delete worktrees older than this
    evidence_ttl_days: int = 30  # Delete evidence files older than this
    max_worktrees: int = 50  # Maximum number of active worktrees

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CleanupConfig":
        """Create a config instance from a dictionary."""
        return cls(
            auto_cleanup_on_merge=data.get("auto_cleanup_on_merge", True),
            worktree_ttl_days=data.get("worktree_ttl_days", 14),
            evidence_ttl_days=data.get("evidence_ttl_days", 30),
            max_worktrees=data.get("max_worktrees", 50),
        )


@dataclass
class MergeConfig:
    """Configuration for merge operations."""

    default_strategy: str = "merge"  # "merge" or "rebase"
    pull_before_merge: bool = True  # git pull --ff-only before merge
    delete_branch_after_merge: bool = True  # Delete branch after merge
    require_pull_success: bool = True  # If pull fails, abort merge (safer default)
    push_after_merge: bool = False  # Push target branch to remote after merge
    squash_merge: bool = True  # Squash commits into single commit
    check_divergence: bool = True  # Check if target branch moved ahead

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MergeConfig":
        """Create a config instance from a dictionary."""
        return cls(
            default_strategy=data.get("default_strategy", "merge"),
            pull_before_merge=data.get("pull_before_merge", True),
            delete_branch_after_merge=data.get("delete_branch_after_merge", True),
            require_pull_success=data.get("require_pull_success", True),
            push_after_merge=data.get("push_after_merge", False),
            squash_merge=data.get("squash_merge", True),
            check_divergence=data.get("check_divergence", True),
        )


@dataclass
class AutonomyConfig:
    """Configuration for full autonomy mode safety rails."""

    max_diff_lines: int = 500
    sensitive_file_patterns: list[str] = field(
        default_factory=lambda: [
            "**/.env*",
            "**/*.pem",
            "**/*.key",
            "**/secrets/**",
            "**/credentials*",
        ]
    )
    require_verification_pass: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomyConfig":
        """Create a config instance from a dictionary."""
        default_patterns = [
            "**/.env*",
            "**/*.pem",
            "**/*.key",
            "**/secrets/**",
            "**/credentials*",
        ]
        return cls(
            max_diff_lines=data.get("max_diff_lines", 500),
            sensitive_file_patterns=data.get("sensitive_file_patterns")
            or default_patterns,
            require_verification_pass=data.get("require_verification_pass", True),
        )


@dataclass
class PlannerFeaturesConfig:
    """Feature flags for the planner."""

    auto_execute: bool = False
    propose_followups: bool = True
    generate_reflections: bool = True
    validate_tickets: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannerFeaturesConfig":
        """Create a config instance from a dictionary."""
        return cls(
            auto_execute=data.get("auto_execute", False),
            propose_followups=data.get("propose_followups", True),
            generate_reflections=data.get("generate_reflections", True),
            validate_tickets=data.get("validate_tickets", False),
        )


@dataclass
class UDARConfig:
    """Configuration for UDAR (Understand-Decide-Act-Validate-Review) agent.

    UDAR is a lean agent architecture for adaptive ticket generation with
    minimal LLM usage (1-2 calls per goal).

    Phase 5 adds production hardening: error handling, timeouts, fallback behavior.
    """

    enabled: bool = False
    enable_incremental_replanning: bool = False
    max_self_correction_iterations: int = 1
    enable_llm_validation: bool = False

    # Incremental replanning settings (Phase 3)
    replan_batch_size: int = 5
    replan_significance_threshold: int = 10
    replan_max_frequency_minutes: int = 30

    # Production hardening settings (Phase 5)
    fallback_to_legacy: bool = True  # Fallback to legacy on UDAR errors
    timeout_seconds: int = 120  # Timeout for UDAR agent execution
    enable_cost_tracking: bool = True  # Track LLM costs in AgentSession
    max_retries_on_error: int = 0  # Retry UDAR on transient errors (0 = no retry)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UDARConfig":
        """Create a config instance from a dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            enable_incremental_replanning=data.get(
                "enable_incremental_replanning", False
            ),
            max_self_correction_iterations=data.get(
                "max_self_correction_iterations", 1
            ),
            enable_llm_validation=data.get("enable_llm_validation", False),
            replan_batch_size=data.get("replan_batch_size", 5),
            replan_significance_threshold=data.get("replan_significance_threshold", 10),
            replan_max_frequency_minutes=data.get("replan_max_frequency_minutes", 30),
            # Phase 5 settings
            fallback_to_legacy=data.get("fallback_to_legacy", True),
            timeout_seconds=data.get("timeout_seconds", 120),
            enable_cost_tracking=data.get("enable_cost_tracking", True),
            max_retries_on_error=data.get("max_retries_on_error", 0),
        )


@dataclass
class PlannerConfig:
    """Configuration for the AI planner.

    The planner automates workflow decisions:
    - Picks next ticket to execute (deterministic)
    - Proposes follow-up tickets for blocked items (LLM)
    - Generates reflection summaries for done tickets (LLM)
    - Generates tickets from goals using agent CLI

    Safety caps prevent runaway follow-up generation:
    - max_followups_per_ticket: Max follow-ups for any single blocked ticket
    - max_followups_per_tick: Max follow-ups created in one tick
    - skip_followup_reasons: Blocker reasons that should NOT trigger follow-ups
    """

    model: str = "cli/claude"
    max_tokens_reflection: int = 300
    max_tokens_followup: int = 500
    timeout: int = 30
    features: PlannerFeaturesConfig = field(default_factory=PlannerFeaturesConfig)
    udar: UDARConfig = field(default_factory=UDARConfig)

    # Agent path for ticket generation (cursor-agent or claude CLI)
    # Auto-detected from PATH; set full path to override
    agent_path: str = "claude"

    # Follow-up caps to prevent spam
    max_followups_per_ticket: int = 2  # Total follow-ups for any blocked ticket
    max_followups_per_tick: int = 3  # Max follow-ups created in one tick

    # Blocker reasons that should NOT trigger follow-ups
    # These are typically prompt/requirements issues, not new tickets
    skip_followup_reasons: list[str] = field(
        default_factory=lambda: [
            "no changes produced",
            "no changes",
            "empty diff",
        ]
    )

    def get_agent_path(self) -> str:
        """Get the expanded agent path."""
        return os.path.expanduser(self.agent_path)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannerConfig":
        """Create a config instance from a dictionary."""
        features_data = data.get("features", {})
        features = (
            PlannerFeaturesConfig.from_dict(features_data)
            if features_data
            else PlannerFeaturesConfig()
        )

        udar_data = data.get("udar", {})
        udar = UDARConfig.from_dict(udar_data) if udar_data else UDARConfig()

        default_skip_reasons = ["no changes produced", "no changes", "empty diff"]

        return cls(
            model=data.get("model", "cli/claude"),
            max_tokens_reflection=data.get("max_tokens_reflection", 300),
            max_tokens_followup=data.get("max_tokens_followup", 500),
            timeout=data.get("timeout", 30),
            features=features,
            udar=udar,
            agent_path=data.get("agent_path", "claude"),
            max_followups_per_ticket=data.get("max_followups_per_ticket", 2),
            max_followups_per_tick=data.get("max_followups_per_tick", 3),
            skip_followup_reasons=data.get("skip_followup_reasons")
            or default_skip_reasons,
        )


@dataclass
class ExecutorProfile:
    """A named executor profile with configurable settings.

    Profiles allow per-executor overrides in smartkanban.yaml:

        executor_profiles:
          fast:
            executor_type: claude
            timeout: 300
            extra_flags: ["--model", "claude-sonnet-4-5-20250929"]
          thorough:
            executor_type: claude
            timeout: 1200
            extra_flags: ["--model", "claude-opus-4-6"]
    """

    name: str
    executor_type: str = "claude"
    timeout: int = 600
    extra_flags: list[str] = field(default_factory=list)
    model: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ExecutorProfile":
        """Create a profile from a dictionary."""
        return cls(
            name=name,
            executor_type=data.get("executor_type", "claude"),
            timeout=data.get("timeout", 600),
            extra_flags=data.get("extra_flags") or [],
            model=data.get("model"),
            env=data.get("env") or {},
        )


@dataclass
class SmartKanbanConfig:
    """Root configuration for Alma Kanban.

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

        planner_config:
          model: "gpt-4o-mini"
          max_tokens_reflection: 300
          max_tokens_followup: 500
          timeout: 30
          features:
            auto_execute: true
            propose_followups: true
            generate_reflections: true

        cleanup_config:
          auto_cleanup_on_merge: true
          worktree_ttl_days: 14
          evidence_ttl_days: 30
          max_worktrees: 50

        merge_config:
          default_strategy: "merge"
          pull_before_merge: true
          delete_branch_after_merge: true

    Legacy Support:
        For backwards compatibility, also supports:
        - verify_commands (top-level) → verify_config.commands
        - auto_transition_on_success → verify_config.on_success
    """

    project: ProjectConfig = field(default_factory=ProjectConfig)
    execute_config: ExecuteConfig = field(default_factory=ExecuteConfig)
    verify_config: VerifyConfig = field(default_factory=VerifyConfig)
    planner_config: PlannerConfig = field(default_factory=PlannerConfig)
    cleanup_config: CleanupConfig = field(default_factory=CleanupConfig)
    merge_config: MergeConfig = field(default_factory=MergeConfig)
    autonomy_config: AutonomyConfig = field(default_factory=AutonomyConfig)
    executor_profiles: dict[str, ExecutorProfile] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SmartKanbanConfig":
        """Create a config instance from a dictionary."""
        # Parse project config
        project_data = data.get("project", {})
        project = (
            ProjectConfig.from_dict(project_data) if project_data else ProjectConfig()
        )

        # Parse execute config
        execute_data = data.get("execute_config", {})
        execute_config = (
            ExecuteConfig.from_dict(execute_data) if execute_data else ExecuteConfig()
        )

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

        # Parse planner config
        planner_data = data.get("planner_config", {})
        planner_config = (
            PlannerConfig.from_dict(planner_data) if planner_data else PlannerConfig()
        )

        # Parse cleanup config
        cleanup_data = data.get("cleanup_config", {})
        cleanup_config = (
            CleanupConfig.from_dict(cleanup_data) if cleanup_data else CleanupConfig()
        )

        # Parse merge config
        merge_data = data.get("merge_config", {})
        merge_config = (
            MergeConfig.from_dict(merge_data) if merge_data else MergeConfig()
        )

        # Parse autonomy config
        autonomy_data = data.get("autonomy_config", {})
        autonomy_config = (
            AutonomyConfig.from_dict(autonomy_data)
            if autonomy_data
            else AutonomyConfig()
        )

        # Parse executor profiles
        profiles_data = data.get("executor_profiles", {})
        executor_profiles = {}
        if isinstance(profiles_data, dict):
            for profile_name, profile_data in profiles_data.items():
                if isinstance(profile_data, dict):
                    executor_profiles[profile_name] = ExecutorProfile.from_dict(
                        profile_name, profile_data
                    )

        return cls(
            project=project,
            execute_config=execute_config,
            verify_config=verify_config,
            planner_config=planner_config,
            cleanup_config=cleanup_config,
            merge_config=merge_config,
            autonomy_config=autonomy_config,
            executor_profiles=executor_profiles,
        )

    # Convenience properties for backwards compatibility
    @property
    def verify_commands(self) -> list[str]:
        """Get verification commands (legacy accessor)."""
        return self.verify_config.commands

    @property
    def auto_transition_on_success(self) -> bool:
        """Get auto-transition setting (legacy accessor).

        DEPRECATED: Always returns False. Tickets must be approved by user
        to transition from needs_human to done.
        """
        return False


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

        # If config file not found at repo_path, try to find it by walking up
        # to the git repo root (handles CWD being a subdirectory like backend/)
        if not (self.repo_path / self.CONFIG_FILENAME).exists():
            try:
                import subprocess

                git_root = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=str(self.repo_path),
                ).stdout.strip()
                if git_root and (Path(git_root) / self.CONFIG_FILENAME).exists():
                    self.repo_path = Path(git_root)
            except Exception:
                pass

    @property
    def config_path(self) -> Path:
        """Get the path to the config file."""
        return self.repo_path / self.CONFIG_FILENAME

    def load_config(self, use_cache: bool = False) -> SmartKanbanConfig:
        """
        Load and parse the smartkanban.yaml configuration.

        Args:
            use_cache: Whether to use cached config if available (default: False for dev).

        Returns:
            SmartKanbanConfig instance with parsed configuration.
            Returns default config if file doesn't exist or is invalid.
        """
        return self._load_config_from_file()

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

    def load_config_with_board_overrides(
        self,
        board_config: dict[str, Any] | None = None,
        use_cache: bool = False,
    ) -> SmartKanbanConfig:
        """Load config from file and apply board-level overrides.

        Args:
            board_config: Optional dict of board-level config overrides.
                         Keys match smartkanban.yaml sections (e.g. execute_config, planner_config).
            use_cache: Whether to use cached config.

        Returns:
            SmartKanbanConfig with board overrides merged in.
        """
        config = self.load_config(use_cache=use_cache)

        if not board_config:
            return config

        # Merge board overrides into the loaded config
        if "execute_config" in board_config and isinstance(
            board_config["execute_config"], dict
        ):
            ec = board_config["execute_config"]
            if "timeout" in ec:
                config.execute_config.timeout = ec["timeout"]
            if "preferred_executor" in ec:
                config.execute_config.preferred_executor = ec["preferred_executor"]
            if "yolo_mode" in ec:
                config.execute_config.yolo_mode = ec["yolo_mode"]

        if "planner_config" in board_config and isinstance(
            board_config["planner_config"], dict
        ):
            pc = board_config["planner_config"]
            if "model" in pc:
                config.planner_config.model = pc["model"]
            if "agent_path" in pc:
                config.planner_config.agent_path = pc["agent_path"]
            if "timeout" in pc:
                config.planner_config.timeout = pc["timeout"]

        if "verify_config" in board_config and isinstance(
            board_config["verify_config"], dict
        ):
            vc = board_config["verify_config"]
            if "commands" in vc:
                config.verify_config.commands = vc["commands"]

        return config

    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._cache.clear()

    # Convenience methods
    def get_verify_commands(self) -> list[str]:
        """Get the list of verification commands."""
        return self.load_config().verify_commands

    def get_verify_on_success(self) -> str:
        """Get the target state when verification succeeds.

        Always returns 'needs_human' - user must approve to move to done.
        """
        return "needs_human"

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

    def get_planner_config(self) -> PlannerConfig:
        """Get the planner configuration."""
        return self.load_config().planner_config

    def get_cleanup_config(self) -> CleanupConfig:
        """Get the cleanup configuration."""
        return self.load_config().cleanup_config

    def get_merge_config(self) -> MergeConfig:
        """Get the merge configuration."""
        return self.load_config().merge_config

    def get_autonomy_config(self) -> AutonomyConfig:
        """Get the autonomy configuration."""
        return self.load_config().autonomy_config

    def get_executor_profiles(self) -> dict[str, ExecutorProfile]:
        """Get all configured executor profiles."""
        return self.load_config().executor_profiles

    def get_executor_profile(self, name: str) -> ExecutorProfile | None:
        """Get a specific executor profile by name."""
        return self.load_config().executor_profiles.get(name)

    def save_executor_profiles(
        self, profiles: list[dict[str, Any]]
    ) -> dict[str, ExecutorProfile]:
        """Save executor profiles to smartkanban.yaml.

        Reads the existing YAML, updates only the executor_profiles section,
        and writes back. Preserves all other config and comments where possible.
        """
        config_path = self.config_path

        # Load existing YAML as raw dict (preserves structure)
        data: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

        # Build profiles dict
        profiles_dict: dict[str, Any] = {}
        for p in profiles:
            name = p.get("name", "").strip()
            if not name:
                continue
            entry: dict[str, Any] = {}
            if p.get("executor_type"):
                entry["executor_type"] = p["executor_type"]
            if p.get("timeout"):
                entry["timeout"] = int(p["timeout"])
            if p.get("extra_flags"):
                entry["extra_flags"] = p["extra_flags"]
            if p.get("model"):
                entry["model"] = p["model"]
            if p.get("env"):
                entry["env"] = p["env"]
            profiles_dict[name] = entry

        data["executor_profiles"] = profiles_dict

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        self.clear_cache()
        return self.get_executor_profiles()
