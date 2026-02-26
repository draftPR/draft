"""Service for full autonomy mode safety checks and auto-actions.

Autonomy mode allows goals to bypass manual gates (ticket approval,
revision approval, merge, follow-up approval) with configurable safety rails.

All auto-actions are recorded as TicketEvents with actor_id="autonomy_service"
for a complete audit trail.
"""

import fnmatch
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.models.enums import ActorType, EventType
from app.models.evidence import Evidence, EvidenceKind
from app.models.goal import Goal
from app.models.revision import Revision
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.config_service import AutonomyConfig, ConfigService

logger = logging.getLogger(__name__)


@dataclass
class AutonomyCheckResult:
    """Result of an autonomy safety check."""

    approved: bool
    reason: str


class AutonomyService:
    """Core safety logic for full autonomy mode.

    Provides both async (FastAPI) and sync (Celery worker) methods.
    """

    def __init__(self, config: AutonomyConfig | None = None):
        if config is None:
            config = ConfigService().get_autonomy_config()
        self.config = config

    # ── Async methods (for FastAPI routes and planner) ──

    async def can_auto_approve_ticket(
        self, db: AsyncSession, ticket: Ticket
    ) -> AutonomyCheckResult:
        """Check if a ticket can be auto-approved (PROPOSED -> PLANNED).

        Checks:
        - goal.autonomy_enabled
        - goal.auto_approve_tickets
        - max_auto_approvals not exceeded
        """
        result = await db.execute(select(Goal).where(Goal.id == ticket.goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            return AutonomyCheckResult(False, "Goal not found")

        return self._check_ticket_approval(goal)

    async def can_auto_approve_revision(
        self, db: AsyncSession, ticket: Ticket, revision: Revision | None = None
    ) -> AutonomyCheckResult:
        """Check if a revision can be auto-approved (VERIFYING -> DONE).

        Checks:
        - goal.autonomy_enabled + goal.auto_approve_revisions
        - All verification evidence has exit_code == 0
        - Diff size < max_diff_lines
        - No sensitive files in diff
        - max_auto_approvals not reached
        """
        result = await db.execute(select(Goal).where(Goal.id == ticket.goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            return AutonomyCheckResult(False, "Goal not found")

        # Load evidence for this ticket
        evidence_result = await db.execute(
            select(Evidence).where(Evidence.ticket_id == ticket.id)
        )
        evidence_list = list(evidence_result.scalars().all())

        return self._check_revision_approval(goal, evidence_list)

    async def can_auto_merge(
        self, db: AsyncSession, ticket: Ticket, repo_path: Path
    ) -> AutonomyCheckResult:
        """Check if a ticket can be auto-merged after DONE.

        Checks:
        - goal.auto_merge
        - Pre-check merge conflicts
        """
        result = await db.execute(select(Goal).where(Goal.id == ticket.goal_id))
        goal = result.scalar_one_or_none()
        if goal is None:
            return AutonomyCheckResult(False, "Goal not found")

        if not goal.autonomy_enabled or not goal.auto_merge:
            return AutonomyCheckResult(False, "Auto-merge not enabled for this goal")

        # Get workspace to find branch name
        ticket_result = await db.execute(
            select(Ticket)
            .where(Ticket.id == ticket.id)
            .options(selectinload(Ticket.workspace))
        )
        ticket_with_ws = ticket_result.scalar_one_or_none()
        if not ticket_with_ws or not ticket_with_ws.workspace:
            return AutonomyCheckResult(False, "No active workspace")

        branch_name = ticket_with_ws.workspace.branch_name
        return self._check_merge_conflicts(repo_path, branch_name)

    async def record_auto_action(
        self,
        db: AsyncSession,
        ticket: Ticket,
        action_type: str,
        details: dict,
        from_state: str | None = None,
        to_state: str | None = None,
    ) -> None:
        """Record an autonomy action as a TicketEvent and increment counter."""
        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.TRANSITIONED.value
            if from_state != to_state
            else EventType.COMMENT.value,
            from_state=from_state or ticket.state,
            to_state=to_state or ticket.state,
            actor_type=ActorType.SYSTEM.value,
            actor_id="autonomy_service",
            reason=f"Auto-{action_type}: {details.get('reason', 'autonomy mode')}",
            payload_json=json.dumps({"autonomy_action": action_type, **details}),
        )
        db.add(event)

        # Increment auto_approval_count on goal
        result = await db.execute(select(Goal).where(Goal.id == ticket.goal_id))
        goal = result.scalar_one_or_none()
        if goal:
            goal.auto_approval_count += 1

    # ── Sync methods (for Celery worker) ──

    def can_auto_approve_ticket_sync(
        self, db: Session, ticket: Ticket
    ) -> AutonomyCheckResult:
        """Sync version of can_auto_approve_ticket for Celery worker."""
        goal = db.query(Goal).filter(Goal.id == ticket.goal_id).first()
        if goal is None:
            return AutonomyCheckResult(False, "Goal not found")
        return self._check_ticket_approval(goal)

    def can_auto_approve_revision_sync(
        self, db: Session, ticket: Ticket
    ) -> AutonomyCheckResult:
        """Sync version of can_auto_approve_revision for Celery worker."""
        goal = db.query(Goal).filter(Goal.id == ticket.goal_id).first()
        if goal is None:
            return AutonomyCheckResult(False, "Goal not found")

        evidence_list = db.query(Evidence).filter(Evidence.ticket_id == ticket.id).all()
        return self._check_revision_approval(goal, evidence_list)

    def record_auto_action_sync(
        self,
        db: Session,
        ticket: Ticket,
        action_type: str,
        details: dict,
        from_state: str | None = None,
        to_state: str | None = None,
    ) -> None:
        """Sync version of record_auto_action for Celery worker."""
        event = TicketEvent(
            ticket_id=ticket.id,
            event_type=EventType.TRANSITIONED.value
            if from_state != to_state
            else EventType.COMMENT.value,
            from_state=from_state or ticket.state,
            to_state=to_state or ticket.state,
            actor_type=ActorType.SYSTEM.value,
            actor_id="autonomy_service",
            reason=f"Auto-{action_type}: {details.get('reason', 'autonomy mode')}",
            payload_json=json.dumps({"autonomy_action": action_type, **details}),
        )
        db.add(event)

        goal = db.query(Goal).filter(Goal.id == ticket.goal_id).first()
        if goal:
            goal.auto_approval_count += 1

    # ── Shared pure logic (no DB) ──

    def _check_ticket_approval(self, goal: Goal) -> AutonomyCheckResult:
        """Check if goal settings allow auto-approving a ticket."""
        if not goal.autonomy_enabled:
            return AutonomyCheckResult(False, "Autonomy not enabled for this goal")
        if not goal.auto_approve_tickets:
            return AutonomyCheckResult(False, "Auto-approve tickets not enabled")
        if (
            goal.max_auto_approvals is not None
            and goal.auto_approval_count >= goal.max_auto_approvals
        ):
            return AutonomyCheckResult(
                False, f"Max auto-approvals reached ({goal.max_auto_approvals})"
            )
        return AutonomyCheckResult(True, "Ticket auto-approval allowed")

    def _check_revision_approval(
        self, goal: Goal, evidence_list: list[Evidence]
    ) -> AutonomyCheckResult:
        """Check if goal settings and evidence allow auto-approving a revision."""
        if not goal.autonomy_enabled:
            return AutonomyCheckResult(False, "Autonomy not enabled for this goal")
        if not goal.auto_approve_revisions:
            return AutonomyCheckResult(False, "Auto-approve revisions not enabled")
        if (
            goal.max_auto_approvals is not None
            and goal.auto_approval_count >= goal.max_auto_approvals
        ):
            return AutonomyCheckResult(
                False, f"Max auto-approvals reached ({goal.max_auto_approvals})"
            )

        # Check verification evidence
        if self.config.require_verification_pass:
            verify_evidence = [
                e
                for e in evidence_list
                if e.kind in (EvidenceKind.VERIFY_META.value, EvidenceKind.VERIFY_META)
            ]
            if verify_evidence:
                for ve in verify_evidence:
                    if ve.exit_code != 0:
                        return AutonomyCheckResult(
                            False, f"Verification failed (exit_code={ve.exit_code})"
                        )

        # Check diff size
        diff_stat_evidence = [
            e
            for e in evidence_list
            if e.kind in (EvidenceKind.GIT_DIFF_STAT.value, EvidenceKind.GIT_DIFF_STAT)
        ]
        if diff_stat_evidence:
            total_lines = self._parse_diff_stat_lines(diff_stat_evidence[-1])
            if total_lines > self.config.max_diff_lines:
                return AutonomyCheckResult(
                    False,
                    f"Diff too large ({total_lines} lines > {self.config.max_diff_lines} max)",
                )

        # Check for sensitive files in diff
        diff_patch_evidence = [
            e
            for e in evidence_list
            if e.kind
            in (EvidenceKind.GIT_DIFF_PATCH.value, EvidenceKind.GIT_DIFF_PATCH)
        ]
        if diff_patch_evidence:
            sensitive = self._check_sensitive_files(diff_patch_evidence[-1])
            if sensitive:
                return AutonomyCheckResult(
                    False,
                    f"Sensitive files detected in diff: {', '.join(sensitive)}",
                )

        return AutonomyCheckResult(True, "Revision auto-approval allowed")

    def _parse_diff_stat_lines(self, evidence: Evidence) -> int:
        """Parse total lines changed from a git diff --stat evidence record.

        The last line of diff stat output looks like:
         N files changed, X insertions(+), Y deletions(-)
        """
        try:
            config_service = ConfigService()
            repo_root = config_service.get_repo_root()
            content_path = repo_root / evidence.stdout_path
            if not content_path.exists():
                return 0
            content = content_path.read_text()
            # Parse last line for total
            lines = content.strip().split("\n")
            if not lines:
                return 0
            last_line = lines[-1]
            total = 0
            # Parse "X insertions(+)" and "Y deletions(-)"
            for part in last_line.split(","):
                part = part.strip()
                if "insertion" in part or "deletion" in part:
                    try:
                        total += int(part.split()[0])
                    except (ValueError, IndexError):
                        pass
            return total
        except Exception:
            logger.debug("Failed to parse diff stat", exc_info=True)
            return 0

    def _check_sensitive_files(self, evidence: Evidence) -> list[str]:
        """Check if any files in a diff patch match sensitive file patterns."""
        try:
            config_service = ConfigService()
            repo_root = config_service.get_repo_root()
            content_path = repo_root / evidence.stdout_path
            if not content_path.exists():
                return []
            content = content_path.read_text()
            # Extract file paths from diff headers (--- a/path and +++ b/path)
            files_in_diff = set()
            for line in content.split("\n"):
                if line.startswith("+++ b/") or line.startswith("--- a/"):
                    path = line[6:]  # Remove "+++ b/" or "--- a/"
                    if path != "/dev/null":
                        files_in_diff.add(path)

            # Match against sensitive patterns
            matches = []
            for file_path in files_in_diff:
                for pattern in self.config.sensitive_file_patterns:
                    if fnmatch.fnmatch(file_path, pattern):
                        matches.append(file_path)
                        break
            return matches
        except Exception:
            logger.debug("Failed to check sensitive files", exc_info=True)
            return []

    def _check_merge_conflicts(
        self, repo_path: Path, branch_name: str
    ) -> AutonomyCheckResult:
        """Pre-check for merge conflicts using git merge --no-commit --no-ff."""
        try:
            # Try merge dry-run
            result = subprocess.run(
                ["git", "merge", "--no-commit", "--no-ff", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Always abort the test merge
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                return AutonomyCheckResult(
                    False,
                    f"Merge conflicts detected: {result.stderr.strip()[:200]}",
                )

            return AutonomyCheckResult(True, "No merge conflicts detected")

        except subprocess.TimeoutExpired:
            return AutonomyCheckResult(False, "Merge conflict check timed out")
        except Exception as e:
            return AutonomyCheckResult(False, f"Merge conflict check failed: {e}")
