"""Service for executing code changes using CLI tools (Claude Code CLI or Cursor CLI)."""

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textwrap import dedent

from app.exceptions import ExecutorNotFoundError


class ExecutorType(str, Enum):
    """Supported executor CLI types."""

    CLAUDE = "claude"
    CURSOR = "cursor"


@dataclass
class ExecutorInfo:
    """Information about an available executor CLI."""

    executor_type: ExecutorType
    command: str
    path: str

    def get_apply_command(self, prompt_file: Path, worktree_path: Path) -> list[str]:
        """
        Get the command to run for applying changes.

        Args:
            prompt_file: Path to the prompt bundle file.
            worktree_path: Path to the worktree directory.

        Returns:
            List of command arguments.
        """
        if self.executor_type == ExecutorType.CLAUDE:
            # Claude Code CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --dangerously-skip-permissions: Skip permission prompts (safe in isolated worktree)
            # - Read the prompt from the file
            prompt_content = prompt_file.read_text()
            return [
                self.command,
                "--print",
                "--dangerously-skip-permissions",
                prompt_content,
            ]
        elif self.executor_type == ExecutorType.CURSOR:
            # Cursor CLI doesn't support headless code generation
            # Opening the editor with the worktree and a marker file
            # Note: This is a fallback - Cursor requires interactive use
            return [self.command, str(worktree_path)]
        else:
            raise ValueError(f"Unknown executor type: {self.executor_type}")

    def supports_headless(self) -> bool:
        """Check if this executor supports headless (non-interactive) operation."""
        return self.executor_type == ExecutorType.CLAUDE


class ExecutorService:
    """Service for detecting and using code executor CLIs."""

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
            "  - Claude Code CLI (recommended): https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview\n"
            "  - Cursor CLI (fallback, opens editor): https://docs.cursor.com/cli"
        )

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

