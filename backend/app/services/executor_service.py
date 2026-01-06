"""Service for executing code changes using CLI tools (Claude Code CLI or Cursor CLI)."""

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import dedent

from app.exceptions import ExecutorNotFoundError


class ExecutorType(str, Enum):
    """Supported executor CLI types."""

    CLAUDE = "claude"  # Headless executor - can run automatically
    CURSOR = "cursor"  # Interactive executor - requires human completion


class ExecutorMode(str, Enum):
    """Execution mode for the executor."""

    HEADLESS = "headless"  # Fully automated, no human intervention
    INTERACTIVE = "interactive"  # Requires human to complete the work


@dataclass
class ExecutorInfo:
    """Information about an available executor CLI."""

    executor_type: ExecutorType
    command: str
    path: str

    @property
    def mode(self) -> ExecutorMode:
        """Get the execution mode for this executor.

        Claude CLI supports headless operation.
        Cursor CLI is interactive - it opens the editor for human completion.
        """
        if self.executor_type == ExecutorType.CLAUDE:
            return ExecutorMode.HEADLESS
        return ExecutorMode.INTERACTIVE

    def is_headless(self) -> bool:
        """Check if this executor supports headless (non-interactive) operation."""
        return self.mode == ExecutorMode.HEADLESS

    def is_interactive(self) -> bool:
        """Check if this executor requires human interaction."""
        return self.mode == ExecutorMode.INTERACTIVE

    def get_apply_command(
        self,
        prompt_file: Path,
        worktree_path: Path,
        yolo_mode: bool = False,
    ) -> list[str]:
        """
        Get the command to run for applying changes.

        Args:
            prompt_file: Path to the prompt bundle file.
            worktree_path: Path to the worktree directory.
            yolo_mode: If True, use --dangerously-skip-permissions (DANGEROUS).
                      Only use when execution is isolated and you accept the risk.

        Returns:
            List of command arguments.
        """
        if self.executor_type == ExecutorType.CLAUDE:
            # Claude Code CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --dangerously-skip-permissions: ONLY if yolo_mode is enabled
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--dangerously-skip-permissions")
            cmd.append(prompt_content)
            return cmd
        elif self.executor_type == ExecutorType.CURSOR:
            # Cursor CLI is INTERACTIVE ONLY
            # It opens the editor with the worktree. User must complete changes manually.
            # The worker will immediately transition to needs_human.
            return [self.command, str(worktree_path)]
        else:
            raise ValueError(f"Unknown executor type: {self.executor_type}")


class ExecutorService:
    """Service for detecting and using code executor CLIs.

    Executor Types:
        - Claude CLI (headless): Can run fully automated. Preferred for CI/automation.
        - Cursor CLI (interactive): Opens editor for human completion. Use as handoff.

    Design Decisions:
        - Claude CLI is preferred for headless operation
        - Cursor CLI is a fallback that prepares workspace + prompt, then hands off to user
        - If only Cursor is available, caller should transition to needs_human
    """

    # CLI names to check in order of preference
    # Claude is preferred because it supports headless operation
    CLI_PREFERENCES = [
        (ExecutorType.CLAUDE, "claude"),
        (ExecutorType.CURSOR, "cursor"),
    ]

    @classmethod
    def detect_executor(cls, preferred: str | None = None) -> ExecutorInfo:
        """
        Detect an available executor CLI.

        Args:
            preferred: Preferred executor type ("cursor" or "claude").
                      If specified and available, it will be used.

        Returns:
            ExecutorInfo with details about the detected CLI.
            IMPORTANT: Check executor_info.is_interactive() - if True, you should
            transition to needs_human instead of expecting automated completion.

        Raises:
            ExecutorNotFoundError: If no supported CLI is found.
        """
        # Build ordered list of executors to check
        cli_order = list(cls.CLI_PREFERENCES)

        # If a preferred executor is specified, move it to the front
        if preferred:
            preferred_lower = preferred.lower()
            for i, (exec_type, cmd) in enumerate(cli_order):
                if exec_type.value == preferred_lower:
                    cli_order.insert(0, cli_order.pop(i))
                    break

        # Check each CLI in order
        for exec_type, cmd in cli_order:
            path = shutil.which(cmd)
            if path:
                return ExecutorInfo(
                    executor_type=exec_type,
                    command=cmd,
                    path=path,
                )

        # No CLI found - raise descriptive error
        raise ExecutorNotFoundError(
            "No supported code executor CLI found. "
            "Please install one of the following:\n"
            "  - Claude Code CLI (recommended for automation): "
            "https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview\n"
            "  - Cursor CLI (interactive, opens editor): https://docs.cursor.com/cli"
        )

    @classmethod
    def detect_headless_executor(cls, preferred: str | None = None) -> ExecutorInfo | None:
        """
        Detect a headless executor CLI only.

        Unlike detect_executor(), this returns None if only interactive
        executors are available (instead of returning them).

        Args:
            preferred: Preferred executor type.

        Returns:
            ExecutorInfo if a headless executor is found, None otherwise.
        """
        try:
            executor = cls.detect_executor(preferred=preferred)
            if executor.is_headless():
                return executor
            return None
        except ExecutorNotFoundError:
            return None

    @classmethod
    def is_available(cls) -> bool:
        """
        Check if any executor CLI is available.

        Returns:
            True if at least one supported CLI is available.
        """
        try:
            cls.detect_executor()
            return True
        except ExecutorNotFoundError:
            return False

    @classmethod
    def is_headless_available(cls) -> bool:
        """
        Check if a headless executor CLI is available.

        Returns:
            True if at least one headless executor is available.
        """
        return cls.detect_headless_executor() is not None


class PromptBundleBuilder:
    """Builder for creating prompt bundles for code execution."""

    PROMPT_FILENAME = "prompt.txt"

    def __init__(self, worktree_path: Path, job_id: str):
        """
        Initialize the prompt bundle builder.

        Args:
            worktree_path: Path to the worktree directory.
            job_id: UUID of the job.
        """
        self.worktree_path = worktree_path
        self.job_id = job_id
        self.job_dir = worktree_path / ".smartkanban" / "jobs" / job_id

    @property
    def prompt_file(self) -> Path:
        """Get the path to the prompt file."""
        return self.job_dir / self.PROMPT_FILENAME

    def build_prompt(
        self,
        ticket_title: str,
        ticket_description: str | None,
        additional_context: str | None = None,
    ) -> Path:
        """
        Build a prompt bundle file for the executor CLI.

        Args:
            ticket_title: Title of the ticket.
            ticket_description: Description of the ticket (may be None).
            additional_context: Optional additional context to include.

        Returns:
            Path to the created prompt file.
        """
        # Ensure the job directory exists
        self.job_dir.mkdir(parents=True, exist_ok=True)

        # Build the prompt content
        prompt_content = self._generate_prompt_content(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            additional_context=additional_context,
        )

        # Write the prompt file
        self.prompt_file.write_text(prompt_content)

        return self.prompt_file

    def _generate_prompt_content(
        self,
        ticket_title: str,
        ticket_description: str | None,
        additional_context: str | None = None,
    ) -> str:
        """
        Generate the content for the prompt bundle.

        Args:
            ticket_title: Title of the ticket.
            ticket_description: Description of the ticket.
            additional_context: Optional additional context.

        Returns:
            Formatted prompt string.
        """
        description_text = ticket_description or "No additional description provided."

        prompt = dedent(f"""\
            # Task: {ticket_title}

            ## Description

            {description_text}

            ## Constraints

            - Make minimal, focused changes to accomplish the task
            - Do NOT modify files that are unrelated to this task
            - Preserve existing code style and conventions
            - Do NOT introduce unnecessary dependencies
            - Keep changes atomic and reviewable

            ## Completion Criteria

            - Code compiles without errors
            - Tests pass (if applicable)
            - Changes are minimal and focused on the task
            - No unrelated modifications

            ## Instructions

            1. Analyze the codebase to understand the current structure
            2. Implement the changes described above
            3. After completing the changes, provide a brief summary explaining:
               - What files were modified
               - What changes were made
               - Why each change was necessary
        """)

        if additional_context:
            prompt += f"\n## Additional Context\n\n{additional_context}\n"

        return prompt

    def get_evidence_dir(self) -> Path:
        """
        Get the evidence directory for this job.

        Returns:
            Path to the evidence directory.
        """
        evidence_dir = self.job_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        return evidence_dir

