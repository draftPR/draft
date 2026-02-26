"""Safe autopilot with configurable safety gates for autonomous execution.

The SafeAutopilot ensures that autonomous execution respects safety constraints
and doesn't make changes that could be dangerous or expensive without human review.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.goal import Goal
from app.models.job import Job
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


class GateAction(StrEnum):
    """What to do when a gate fails."""
    BLOCK = "block"      # Stop execution, mark as blocked
    PAUSE = "pause"      # Pause for human review
    ALERT = "alert"      # Alert but continue


@dataclass
class GateContext:
    """Context information for gate evaluation."""
    ticket: Ticket
    goal: Goal | None
    total_cost_so_far: float
    total_files_changed: int
    total_lines_changed: int
    all_tests_passed: bool
    modified_files: list[str]
    budget_limit: float | None

    def __post_init__(self):
        if self.modified_files is None:
            self.modified_files = []


@dataclass
class GateResult:
    """Result of evaluating a safety gate."""
    gate_name: str
    passed: bool
    action: GateAction
    reason: str | None = None
    details: dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class SafetyGate:
    """Base class for safety gates."""

    def __init__(self, name: str, action: GateAction = GateAction.BLOCK):
        self.name = name
        self.action = action

    async def evaluate(self, context: GateContext) -> GateResult:
        """Evaluate the gate against the context."""
        raise NotImplementedError


class TestsPassedGate(SafetyGate):
    """Gate that checks if all tests passed."""

    def __init__(self, action: GateAction = GateAction.BLOCK):
        super().__init__("tests_passed", action)

    async def evaluate(self, context: GateContext) -> GateResult:
        if context.all_tests_passed:
            return GateResult(
                gate_name=self.name,
                passed=True,
                action=self.action
            )
        else:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=self.action,
                reason="Not all verification tests passed",
                details={"tests_passed": context.all_tests_passed}
            )


class DiffSizeGate(SafetyGate):
    """Gate that checks if diff size is within threshold."""

    def __init__(
        self,
        max_files: int = 50,
        max_lines: int = 1000,
        action: GateAction = GateAction.PAUSE
    ):
        super().__init__("diff_size_threshold", action)
        self.max_files = max_files
        self.max_lines = max_lines

    async def evaluate(self, context: GateContext) -> GateResult:
        if context.total_files_changed > self.max_files:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=self.action,
                reason=f"Too many files changed: {context.total_files_changed} > {self.max_files}",
                details={
                    "files_changed": context.total_files_changed,
                    "max_files": self.max_files
                }
            )

        if context.total_lines_changed > self.max_lines:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=self.action,
                reason=f"Too many lines changed: {context.total_lines_changed} > {self.max_lines}",
                details={
                    "lines_changed": context.total_lines_changed,
                    "max_lines": self.max_lines
                }
            )

        return GateResult(
            gate_name=self.name,
            passed=True,
            action=self.action,
            details={
                "files_changed": context.total_files_changed,
                "lines_changed": context.total_lines_changed
            }
        )


class SensitiveFilesGate(SafetyGate):
    """Gate that checks for modifications to sensitive files."""

    # Files that should never be modified without human review
    SENSITIVE_PATTERNS = [
        ".env",
        "credentials",
        "secrets",
        "password",
        ".key",
        ".pem",
        ".crt",
        "api_key",
        "token",
        "config/production",
        "database.yml",
        "production.yml",
    ]

    def __init__(self, action: GateAction = GateAction.BLOCK):
        super().__init__("no_sensitive_files", action)

    async def evaluate(self, context: GateContext) -> GateResult:
        sensitive_files = []

        for file_path in context.modified_files:
            file_lower = file_path.lower()
            if any(pattern in file_lower for pattern in self.SENSITIVE_PATTERNS):
                sensitive_files.append(file_path)

        if sensitive_files:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=self.action,
                reason=f"Modified sensitive files: {', '.join(sensitive_files)}",
                details={"sensitive_files": sensitive_files}
            )

        return GateResult(
            gate_name=self.name,
            passed=True,
            action=self.action
        )


class BudgetGate(SafetyGate):
    """Gate that checks if budget is within limits."""

    def __init__(
        self,
        warning_threshold: float = 0.8,
        action: GateAction = GateAction.PAUSE
    ):
        super().__init__("cost_budget", action)
        self.warning_threshold = warning_threshold

    async def evaluate(self, context: GateContext) -> GateResult:
        if context.budget_limit is None:
            # No budget set, pass
            return GateResult(
                gate_name=self.name,
                passed=True,
                action=self.action,
                details={"budget_set": False}
            )

        if context.budget_limit <= 0:
            # Unlimited budget
            return GateResult(
                gate_name=self.name,
                passed=True,
                action=self.action,
                details={"budget_unlimited": True}
            )

        budget_used_pct = context.total_cost_so_far / context.budget_limit

        if budget_used_pct >= 1.0:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=GateAction.BLOCK,  # Always block on exceeded budget
                reason=f"Budget exceeded: ${context.total_cost_so_far:.2f} >= ${context.budget_limit:.2f}",
                details={
                    "total_cost": context.total_cost_so_far,
                    "budget_limit": context.budget_limit,
                    "budget_used_pct": budget_used_pct
                }
            )

        if budget_used_pct >= self.warning_threshold:
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=self.action,
                reason=f"Budget warning: {budget_used_pct*100:.1f}% used (${context.total_cost_so_far:.2f} / ${context.budget_limit:.2f})",
                details={
                    "total_cost": context.total_cost_so_far,
                    "budget_limit": context.budget_limit,
                    "budget_used_pct": budget_used_pct,
                    "warning_threshold": self.warning_threshold
                }
            )

        return GateResult(
            gate_name=self.name,
            passed=True,
            action=self.action,
            details={
                "total_cost": context.total_cost_so_far,
                "budget_limit": context.budget_limit,
                "budget_used_pct": budget_used_pct
            }
        )


class CustomGate(SafetyGate):
    """Custom gate with user-defined evaluation function."""

    def __init__(
        self,
        name: str,
        check_func: Callable[[GateContext], bool],
        action: GateAction = GateAction.PAUSE,
        failure_message: str = "Custom gate check failed"
    ):
        super().__init__(name, action)
        self.check_func = check_func
        self.failure_message = failure_message

    async def evaluate(self, context: GateContext) -> GateResult:
        try:
            passed = self.check_func(context)

            if passed:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    action=self.action
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    action=self.action,
                    reason=self.failure_message
                )
        except Exception as e:
            logger.exception(f"Custom gate {self.name} evaluation failed")
            return GateResult(
                gate_name=self.name,
                passed=False,
                action=GateAction.BLOCK,
                reason=f"Gate evaluation error: {str(e)}"
            )


class SafeAutopilot:
    """
    Safe autopilot with configurable safety gates.

    Ensures autonomous execution respects safety constraints before continuing.
    """

    # Default gates applied to all executions
    DEFAULT_GATES = [
        TestsPassedGate(action=GateAction.BLOCK),
        DiffSizeGate(max_files=50, max_lines=1000, action=GateAction.PAUSE),
        SensitiveFilesGate(action=GateAction.BLOCK),
        BudgetGate(warning_threshold=0.8, action=GateAction.PAUSE),
    ]

    def __init__(self, db: AsyncSession, gates: list[SafetyGate] | None = None):
        self.db = db
        self.gates = gates if gates is not None else self.DEFAULT_GATES.copy()

    def add_gate(self, gate: SafetyGate):
        """Add a custom gate to the autopilot."""
        self.gates.append(gate)

    def remove_gate(self, gate_name: str):
        """Remove a gate by name."""
        self.gates = [g for g in self.gates if g.name != gate_name]

    async def check_gates(self, ticket: Ticket) -> list[GateResult]:
        """Check all safety gates for a ticket.

        Returns:
            List of GateResult objects (one per gate)
        """
        # Build context from ticket and related data
        context = await self._build_context(ticket)

        results = []
        for gate in self.gates:
            try:
                result = await gate.evaluate(context)
                results.append(result)

                # Log gate results
                if not result.passed:
                    logger.warning(
                        f"Gate {gate.name} failed for ticket {ticket.id}: {result.reason}"
                    )
            except Exception as e:
                logger.exception(f"Gate {gate.name} evaluation crashed")
                results.append(GateResult(
                    gate_name=gate.name,
                    passed=False,
                    action=GateAction.BLOCK,
                    reason=f"Gate evaluation crashed: {str(e)}"
                ))

        return results

    async def should_continue(self, ticket: Ticket) -> tuple[bool, list[GateResult]]:
        """
        Check if autopilot should continue with this ticket.

        Returns:
            (can_continue, gate_results)
        """
        results = await self.check_gates(ticket)

        # Check for any blocking failures
        blocked = any(
            not r.passed and r.action == GateAction.BLOCK
            for r in results
        )

        # Check for any pause requests
        paused = any(
            not r.passed and r.action == GateAction.PAUSE
            for r in results
        )

        can_continue = not blocked and not paused

        return can_continue, results

    async def _build_context(self, ticket: Ticket) -> GateContext:
        """Build gate evaluation context from ticket data."""
        # Get goal
        goal = None
        if ticket.goal_id:
            result = await self.db.execute(
                select(Goal)
                .where(Goal.id == ticket.goal_id)
                .options(selectinload(Goal.cost_budget))
            )
            goal = result.scalar_one_or_none()

        # Calculate costs so far for this goal
        total_cost = 0.0
        budget_limit = None

        if goal:
            # Get all jobs for this goal's tickets
            from app.models.agent_session import AgentSession

            result = await self.db.execute(
                select(AgentSession)
                .join(Ticket, Ticket.id == AgentSession.ticket_id)
                .where(Ticket.goal_id == goal.id)
            )
            sessions = result.scalars().all()
            total_cost = sum(s.cost_usd or 0.0 for s in sessions)

            if goal.cost_budget:
                budget_limit = goal.cost_budget.total_budget

        # Get file changes from ticket's jobs
        modified_files = []
        total_files_changed = 0
        total_lines_changed = 0

        from app.models.evidence import Evidence
        result = await self.db.execute(
            select(Evidence)
            .join(Job, Job.id == Evidence.job_id)
            .where(Job.ticket_id == ticket.id)
            .where(Evidence.kind == "diff_stat")
        )
        diff_evidences = result.scalars().all()

        for evidence in diff_evidences:
            # Parse diff stat to get file count and line changes
            # Format: "3 files changed, 45 insertions(+), 12 deletions(-)"
            if evidence.content:
                import re
                files_match = re.search(r'(\d+) files? changed', evidence.content)
                if files_match:
                    total_files_changed += int(files_match.group(1))

                insertions_match = re.search(r'(\d+) insertions?', evidence.content)
                deletions_match = re.search(r'(\d+) deletions?', evidence.content)

                if insertions_match:
                    total_lines_changed += int(insertions_match.group(1))
                if deletions_match:
                    total_lines_changed += int(deletions_match.group(1))

        # Get list of modified files from diff patches
        result = await self.db.execute(
            select(Evidence)
            .join(Job, Job.id == Evidence.job_id)
            .where(Job.ticket_id == ticket.id)
            .where(Evidence.kind == "diff_patch")
        )
        patch_evidences = result.scalars().all()

        for evidence in patch_evidences:
            if evidence.content:
                # Extract file paths from diff headers
                import re
                file_matches = re.findall(r'^\+\+\+ b/(.+)$', evidence.content, re.MULTILINE)
                modified_files.extend(file_matches)

        # Check if tests passed
        all_tests_passed = await self._check_tests_passed(ticket)

        return GateContext(
            ticket=ticket,
            goal=goal,
            total_cost_so_far=total_cost,
            total_files_changed=total_files_changed,
            total_lines_changed=total_lines_changed,
            all_tests_passed=all_tests_passed,
            modified_files=modified_files,
            budget_limit=budget_limit
        )

    async def _check_tests_passed(self, ticket: Ticket) -> bool:
        """Check if all verification tests passed for this ticket."""
        # Get verification jobs for this ticket
        result = await self.db.execute(
            select(Job)
            .where(Job.ticket_id == ticket.id)
            .where(Job.kind == "verify")
        )
        verify_jobs = result.scalars().all()

        if not verify_jobs:
            # No verification run yet
            return False

        # Check if latest verification job succeeded
        latest_verify = max(verify_jobs, key=lambda j: j.created_at)
        return latest_verify.status == "succeeded"


def create_default_autopilot(db: AsyncSession) -> SafeAutopilot:
    """Create a SafeAutopilot with default gates."""
    return SafeAutopilot(db, gates=SafeAutopilot.DEFAULT_GATES.copy())


def create_yolo_autopilot(db: AsyncSession) -> SafeAutopilot:
    """Create a YOLO autopilot with minimal gates (only tests and budget hard limits)."""
    gates = [
        TestsPassedGate(action=GateAction.BLOCK),
        BudgetGate(warning_threshold=1.0, action=GateAction.BLOCK),  # Only block on exceeded
    ]
    return SafeAutopilot(db, gates=gates)


def create_strict_autopilot(db: AsyncSession) -> SafeAutopilot:
    """Create a strict autopilot with tight constraints."""
    gates = [
        TestsPassedGate(action=GateAction.BLOCK),
        DiffSizeGate(max_files=20, max_lines=500, action=GateAction.BLOCK),
        SensitiveFilesGate(action=GateAction.BLOCK),
        BudgetGate(warning_threshold=0.5, action=GateAction.PAUSE),
    ]
    return SafeAutopilot(db, gates=gates)
