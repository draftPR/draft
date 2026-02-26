"""Service for executing code changes using CLI tools (Claude, Codex, Gemini, Cursor)."""

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from textwrap import dedent

from app.exceptions import ExecutorNotFoundError


class ExecutorType(StrEnum):
    """Supported executor CLI types."""

    CLAUDE = "claude"  # Headless executor - can run automatically
    CODEX = "codex"  # Headless executor - OpenAI Codex CLI
    GEMINI = "gemini"  # Headless executor - Google Gemini CLI
    DROID = "droid"  # Headless executor - Droid CLI
    QWEN = "qwen"  # Headless executor - Qwen Code CLI
    OPENCODE = "opencode"  # Headless executor - OpenCode CLI
    AMP = "amp"  # Headless executor - Amp (Sourcegraph) CLI
    CURSOR_AGENT = "cursor-agent"  # Headless executor - Cursor Agent CLI
    CURSOR = "cursor"  # Interactive executor - requires human completion


class ExecutorMode(StrEnum):
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

        Claude CLI and Cursor Agent CLI support headless operation.
        Cursor CLI is interactive - it opens the editor for human completion.
        """
        if self.executor_type in (
            ExecutorType.CLAUDE,
            ExecutorType.CODEX,
            ExecutorType.GEMINI,
            ExecutorType.DROID,
            ExecutorType.QWEN,
            ExecutorType.OPENCODE,
            ExecutorType.AMP,
            ExecutorType.CURSOR_AGENT,
        ):
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
        **kwargs,
    ) -> tuple[list[str], str | None]:
        """
        Get the command to run for applying changes.

        Returns a tuple of (command_args, stdin_input). The prompt content is
        passed via stdin instead of as a CLI argument to avoid exceeding
        ARG_MAX (~130KB on most systems) with large prompts.

        Args:
            prompt_file: Path to the prompt bundle file.
            worktree_path: Path to the worktree directory.
            yolo_mode: If True, use --dangerously-skip-permissions (DANGEROUS).
                      Only use when execution is isolated and you accept the risk.

        Returns:
            Tuple of (command args list, stdin content or None).
        """
        if self.executor_type == ExecutorType.CLAUDE:
            # Claude Code CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --dangerously-skip-permissions: ONLY if yolo_mode is enabled
            # Prompt is piped via stdin to avoid ARG_MAX limits
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--dangerously-skip-permissions")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.CURSOR_AGENT:
            # Cursor Agent CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --output-format=stream-json: Stream JSON output line-by-line for real-time logs
            # - --trust: Trust the workspace directory (required for Cursor Agent to execute)
            # - --force: Allow all commands without prompting (like YOLO mode)
            # - --workspace: Set the working directory
            # Prompt is piped via stdin to avoid ARG_MAX limits
            prompt_content = prompt_file.read_text()
            cmd = [
                self.command,
                "--print",
                "--output-format=stream-json",
                "--trust",
                "--workspace",
                str(worktree_path),
            ]
            if yolo_mode:
                cmd.append("--force")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.CODEX:
            # OpenAI Codex CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --auto-edit: Automatically apply edits to files
            # - --full-auto: ONLY if yolo_mode is enabled (skip all confirmations)
            # Prompt is piped via stdin to avoid ARG_MAX limits
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print", "--auto-edit"]
            if yolo_mode:
                cmd.append("--full-auto")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.GEMINI:
            # Google Gemini CLI with non-interactive mode:
            # - --print: Non-interactive mode that prints response and exits
            # - --yolo: ONLY if yolo_mode is enabled (skip all confirmations)
            # Prompt is piped via stdin to avoid ARG_MAX limits
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--yolo")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.DROID:
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--dangerously-skip-permissions")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.QWEN:
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--yolo")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.OPENCODE:
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--yolo")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.AMP:
            prompt_content = prompt_file.read_text()
            cmd = [self.command, "--print"]
            if yolo_mode:
                cmd.append("--yolo")
            return cmd, prompt_content
        elif self.executor_type == ExecutorType.CURSOR:
            # Cursor CLI is INTERACTIVE ONLY
            # It opens the editor with the worktree. User must complete changes manually.
            # The worker will immediately transition to needs_human.
            return [self.command, str(worktree_path)], None
        else:
            raise ValueError(f"Unknown executor type: {self.executor_type}")


class ExecutorService:
    """Service for detecting and using code executor CLIs.

    Executor Types:
        - Claude CLI (headless): Can run fully automated. Preferred for CI/automation.
        - Codex CLI (headless): OpenAI's Codex CLI for automated code changes.
        - Gemini CLI (headless): Google's Gemini CLI for automated code changes.
        - Cursor Agent CLI (headless): Can run fully automated via cursor-agent.
        - Cursor CLI (interactive): Opens editor for human completion. Use as handoff.

    Design Decisions:
        - Claude CLI is preferred for headless operation
        - Codex and Gemini are alternative headless executors
        - Cursor Agent CLI is another headless executor
        - Cursor CLI is a fallback that prepares workspace + prompt, then hands off to user
        - If only Cursor is available, caller should transition to needs_human
    """

    # CLI names to check in order of preference
    # Claude, Codex, Gemini, and cursor-agent are preferred because they support headless operation
    CLI_PREFERENCES = [
        (ExecutorType.CLAUDE, "claude"),
        (ExecutorType.CODEX, "codex"),
        (ExecutorType.GEMINI, "gemini"),
        (ExecutorType.DROID, "droid"),
        (ExecutorType.QWEN, "qwen"),
        (ExecutorType.OPENCODE, "opencode"),
        (ExecutorType.AMP, "amp"),
        (ExecutorType.CURSOR_AGENT, "cursor-agent"),
        (ExecutorType.CURSOR, "cursor"),
    ]

    # Common paths to check for cursor-agent (not always in PATH)
    CURSOR_AGENT_PATHS = [
        "~/.local/bin/cursor-agent",
        "/usr/local/bin/cursor-agent",
        "/opt/homebrew/bin/cursor-agent",
    ]

    @classmethod
    def _find_cursor_agent(cls, config_path: str | None = None) -> str | None:
        """Find cursor-agent CLI, checking config path and common locations.

        Args:
            config_path: Optional custom path from config.

        Returns:
            Full path to cursor-agent if found, None otherwise.
        """
        # Check config path first
        if config_path:
            expanded = os.path.expanduser(config_path)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded

        # Check common installation paths
        for path in cls.CURSOR_AGENT_PATHS:
            expanded = os.path.expanduser(path)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded

        # Fall back to PATH
        return shutil.which("cursor-agent")

    @classmethod
    def detect_executor(
        cls, preferred: str | None = None, agent_path: str | None = None
    ) -> ExecutorInfo:
        """
        Detect an available executor CLI.

        Args:
            preferred: Preferred executor type ("cursor" or "claude").
                      If specified and available, it will be used.
            agent_path: Custom path for cursor-agent (from config).

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
            for i, (exec_type, _cmd) in enumerate(cli_order):
                if exec_type.value == preferred_lower:
                    cli_order.insert(0, cli_order.pop(i))
                    break

        # Check each CLI in order
        for exec_type, cmd in cli_order:
            if exec_type == ExecutorType.CURSOR_AGENT:
                # Use custom detection for cursor-agent
                path = cls._find_cursor_agent(agent_path)
            else:
                path = shutil.which(cmd)

            if path:
                return ExecutorInfo(
                    executor_type=exec_type,
                    command=path,  # Use full path for cursor-agent
                    path=path,
                )

        # No CLI found - raise descriptive error
        raise ExecutorNotFoundError(
            "No supported code executor CLI found. "
            "Please install one of the following:\n"
            "  - Claude Code CLI (recommended): "
            "https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview\n"
            "  - Codex CLI (OpenAI): https://github.com/openai/codex\n"
            "  - Gemini CLI (Google): https://github.com/google/gemini-cli\n"
            "  - Droid CLI: https://github.com/anthropics/droid\n"
            "  - Qwen Code CLI: https://github.com/QwenLM/qwen-agent\n"
            "  - OpenCode CLI: https://github.com/opencode-ai/opencode\n"
            "  - Amp CLI (Sourcegraph): https://github.com/sourcegraph/amp\n"
            "  - Cursor Agent CLI: Set agent_path in smartkanban.yaml\n"
            "  - Cursor CLI (interactive, opens editor): https://docs.cursor.com/cli"
        )

    @classmethod
    def detect_headless_executor(
        cls, preferred: str | None = None, agent_path: str | None = None
    ) -> ExecutorInfo | None:
        """
        Detect a headless executor CLI only.

        Unlike detect_executor(), this returns None if only interactive
        executors are available (instead of returning them).

        Args:
            preferred: Preferred executor type.
            agent_path: Custom path for cursor-agent (from config).

        Returns:
            ExecutorInfo if a headless executor is found, None otherwise.
        """
        try:
            executor = cls.detect_executor(preferred=preferred, agent_path=agent_path)
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
        feedback_bundle: dict | None = None,
        related_tickets_context: dict | None = None,
        verify_commands: list[str] | None = None,
    ) -> Path:
        """
        Build a prompt bundle file for the executor CLI.

        Args:
            ticket_title: Title of the ticket.
            ticket_description: Description of the ticket (may be None).
            additional_context: Optional additional context to include.
            feedback_bundle: Optional feedback from previous revision review.
            related_tickets_context: Optional context about related tickets and dependencies.
                Expected format: {
                    "dependencies": [{"title": str, "state": str}],  # tickets this depends on
                    "completed_tickets": [{"title": str, "description": str}],  # already done
                    "goal_title": str  # optional goal title
                }
            verify_commands: Current verification commands from smartkanban.yaml.

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
            feedback_bundle=feedback_bundle,
            related_tickets_context=related_tickets_context,
            verify_commands=verify_commands,
        )

        # Write the prompt file
        self.prompt_file.write_text(prompt_content)

        return self.prompt_file

    def _generate_prompt_content(
        self,
        ticket_title: str,
        ticket_description: str | None,
        additional_context: str | None = None,
        feedback_bundle: dict | None = None,
        related_tickets_context: dict | None = None,
        verify_commands: list[str] | None = None,
    ) -> str:
        """
        Generate the content for the prompt bundle.

        Args:
            ticket_title: Title of the ticket.
            ticket_description: Description of the ticket.
            additional_context: Optional additional context.
            feedback_bundle: Optional feedback from previous revision review.
            related_tickets_context: Optional context about related tickets.
            verify_commands: Current verification commands from smartkanban.yaml.

        Returns:
            Formatted prompt string.
        """
        description_text = ticket_description or "No additional description provided."

        prompt = dedent(f"""\
            # Task: {ticket_title}

            ## Description

            {description_text}
        """)

        # Add related tickets context if provided
        if related_tickets_context:
            prompt += self._format_related_tickets_section(related_tickets_context)

        prompt += dedent("""\
            ## Constraints

            - **CRITICAL**: Analyze the codebase structure FIRST before making changes
            - If the ticket mentions specific file paths (e.g., `app/utils/file.py`), check if that structure exists
            - Adapt paths to match the ACTUAL project structure (don't blindly create new directories)
            - If paths don't match reality, use the existing structure instead
            - Make minimal, focused changes to accomplish the task
            - Do NOT modify files that are unrelated to this task
            - Preserve existing code style and conventions
            - Do NOT introduce unnecessary dependencies
            - Keep changes atomic and reviewable
        """)

        # Add revision feedback if present
        if feedback_bundle:
            prompt += self._format_feedback_section(feedback_bundle)

        prompt += dedent("""\
            ## Completion Criteria

            - Code compiles without errors
            - Tests pass (if applicable)
            - Changes are minimal and focused on the task
            - No unrelated modifications
        """)

        if feedback_bundle:
            prompt += "            - All review feedback has been addressed\n"

        prompt += dedent("""\
            ## Instructions

            1. **First, explore the codebase** to understand:
               - The current directory structure
               - Naming conventions and patterns
               - Where similar functionality already exists
               - Dependencies and existing modules

            2. **Validate the approach**:
               - If the ticket mentions specific paths, verify they match the actual structure
               - If paths don't exist, decide: create them OR adapt to existing structure
               - Choose the approach that's most consistent with the codebase

            3. **Implement the changes** described in the task

            4. **Provide a summary** explaining:
               - What files were modified or created
               - What changes were made
               - Why each change was necessary
               - Any path adaptations you made from the ticket description
        """)

        # Add verification scoping instructions
        if verify_commands:
            commands_str = "\n".join(f"  - `{cmd}`" for cmd in verify_commands)
            prompt += dedent(f"""\
            ## Verification Setup

            After implementing your changes, the following verification commands will run:
            {commands_str}

            **IMPORTANT**: If the verification commands above run a broad test suite (e.g., the
            entire test file), you MUST update `smartkanban.yaml` in this worktree to scope the
            `verify_config.commands` to ONLY the tests relevant to your changes. This prevents
            unrelated test failures from blocking your ticket.

            For example, if you fixed `fibonacci` and `is_prime`, update the verify config to:
            ```yaml
            verify_config:
              commands:
                - "python -m pytest -q test_calculator.py::TestFibonacci test_calculator.py::TestIsPrime"
            ```

            Scope the verify commands to the test classes/functions that cover your changes.
            """)

        if additional_context:
            prompt += f"\n## Additional Context\n\n{additional_context}\n"

        return prompt

    def _format_related_tickets_section(self, related_tickets_context: dict) -> str:
        """
        Format related tickets context as a prompt section.

        Args:
            related_tickets_context: Dictionary with dependencies and completed tickets.

        Returns:
            Formatted related tickets section for the prompt.
        """
        section = "\n## Related Tickets Context\n\n"

        goal_title = related_tickets_context.get("goal_title")
        if goal_title:
            section += f"**Goal**: {goal_title}\n\n"

        # Add completed tickets for context
        completed_tickets = related_tickets_context.get("completed_tickets", [])
        if completed_tickets:
            section += "### Previously Completed Tickets\n\n"
            section += "These tickets in the same goal have already been completed:\n\n"
            for ticket in completed_tickets:
                section += f"- **{ticket['title']}**"
                if ticket.get("description"):
                    # Truncate long descriptions
                    desc = ticket["description"]
                    if len(desc) > 150:
                        desc = desc[:150] + "..."
                    section += f": {desc}"
                section += "\n"
            section += "\n**Important**: Build upon this existing work. Don't recreate what's already done.\n\n"

        # Add dependency information
        dependencies = related_tickets_context.get("dependencies", [])
        if dependencies:
            section += "### Dependencies\n\n"
            section += (
                "This ticket depends on the following tickets being completed:\n\n"
            )
            for dep in dependencies:
                section += f"- **{dep['title']}** (Status: {dep['state']})\n"
            section += "\n**Note**: You can assume dependencies are complete and build upon their work.\n\n"

        return section

    def _format_feedback_section(self, feedback_bundle: dict) -> str:
        """
        Format the feedback bundle as a prompt section.

        Args:
            feedback_bundle: The feedback bundle dict.

        Returns:
            Formatted feedback section for the prompt.
        """
        section = "\n## Previous Revision Feedback\n\n"
        section += f"**Revision #{feedback_bundle.get('revision_number', '?')} was reviewed and changes were requested.**\n\n"

        # Add overall summary
        summary = feedback_bundle.get("summary", "")
        if summary:
            section += f"### Reviewer Summary\n\n{summary}\n\n"

        # Add inline comments
        comments = feedback_bundle.get("comments", [])
        if comments:
            section += "### Inline Comments to Address\n\n"
            for comment in comments:
                file_path = comment.get("file_path", "unknown")
                line_number = comment.get("line_number", "?")
                body = comment.get("body", "")
                line_content = comment.get("line_content", "")
                section += f"- **{file_path}:{line_number}**: {body}\n"
                if line_content:
                    section += f"  - Line content: `{line_content}`\n"
            section += "\n"

        section += "**Important**: Address ALL feedback above while preserving correct changes from the previous revision.\n\n"

        return section

    def get_evidence_dir(self) -> Path:
        """
        Get the evidence directory for this job.

        Returns:
            Path to the evidence directory.
        """
        evidence_dir = self.job_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        return evidence_dir
