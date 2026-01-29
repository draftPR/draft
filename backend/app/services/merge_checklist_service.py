"""Service for generating and managing merge readiness checklists."""

import json
import logging
from typing import Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ResourceNotFoundError
from app.models.merge_checklist import MergeChecklist
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.job import Job
from app.models.evidence import Evidence
from app.models.revision import Revision
from app.state_machine import TicketState, JobStatus

logger = logging.getLogger(__name__)


class MergeChecklistService:
    """Generate and track merge readiness checklist."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_or_update_checklist(self, goal_id: str) -> MergeChecklist:
        """Generate or update the merge checklist for a goal.

        Automatically checks:
        - All tests passed
        - Files/lines changed count
        - Total cost
        - Budget status

        Returns:
            MergeChecklist instance
        """
        # Get existing checklist or create new
        result = await self.db.execute(
            select(MergeChecklist).where(MergeChecklist.goal_id == goal_id)
        )
        checklist = result.scalar_one_or_none()

        if not checklist:
            checklist = MergeChecklist(goal_id=goal_id)
            self.db.add(checklist)

        # Run automatic checks
        await self._update_auto_checks(checklist, goal_id)

        # Generate rollback plan if not exists
        if not checklist.rollback_plan_json:
            rollback_plan = await self._generate_rollback_plan(goal_id)
            checklist.rollback_plan_json = json.dumps(rollback_plan)
            checklist.risk_level = rollback_plan["risk_level"]

        # Update ready status
        checklist.ready_to_merge = checklist.is_ready_to_merge()

        await self.db.flush()
        await self.db.refresh(checklist)

        return checklist

    async def _update_auto_checks(self, checklist: MergeChecklist, goal_id: str):
        """Update automatic checks by querying system state."""
        # Get all tickets for this goal
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.goal_id == goal_id)
            .options(
                selectinload(Ticket.jobs).selectinload(Job.evidence),
                selectinload(Ticket.revisions)
            )
        )
        tickets = list(result.scalars().all())

        # Check 1: All tests passed
        checklist.all_tests_passed = await self._check_all_tests_passed(tickets)

        # Check 2: Count files and lines changed
        file_stats = await self._count_changes(tickets)
        checklist.total_files_changed = file_stats["files"]
        checklist.total_lines_changed = file_stats["lines"]

        # Check 3: Calculate total cost
        checklist.total_cost_usd = await self._calculate_cost(goal_id)

        # Check 4: Check budget
        checklist.budget_exceeded = await self._check_budget_exceeded(goal_id)

    async def _check_all_tests_passed(self, tickets: List[Ticket]) -> bool:
        """Check if all verification jobs succeeded."""
        for ticket in tickets:
            # Skip tickets that aren't done yet
            if ticket.state != TicketState.DONE.value:
                return False

            # Find most recent verify job
            verify_jobs = [j for j in ticket.jobs if j.job_type == "verify"]
            if not verify_jobs:
                return False

            latest_verify = max(verify_jobs, key=lambda j: j.created_at)
            if latest_verify.status != JobStatus.SUCCEEDED.value:
                return False

        return True

    async def _count_changes(self, tickets: List[Ticket]) -> Dict[str, int]:
        """Count total files and lines changed across all tickets."""
        total_files = set()
        total_lines = 0

        for ticket in tickets:
            # Get diffs from revisions
            for revision in ticket.revisions:
                if revision.diff_stat_evidence_id:
                    # Parse diff stat from evidence
                    stat_result = await self.db.execute(
                        select(Evidence).where(Evidence.id == revision.diff_stat_evidence_id)
                    )
                    stat_evidence = stat_result.scalar_one_or_none()

                    if stat_evidence and stat_evidence.stdout_path:
                        # Parse diff stat (format: "X files changed, Y insertions(+), Z deletions(-)")
                        try:
                            with open(stat_evidence.stdout_path, 'r') as f:
                                stat_line = f.read().strip()
                                # Simple parsing
                                if "files changed" in stat_line or "file changed" in stat_line:
                                    parts = stat_line.split(",")
                                    files_part = parts[0].strip().split()[0]
                                    total_files.add(f"{ticket.id}:{files_part}")

                                    # Count insertions and deletions
                                    for part in parts[1:]:
                                        if "insertion" in part or "deletion" in part:
                                            count = int(part.strip().split()[0])
                                            total_lines += count
                        except Exception as e:
                            logger.warning(f"Failed to parse diff stat: {e}")

        return {
            "files": len(total_files),
            "lines": total_lines
        }

    async def _calculate_cost(self, goal_id: str) -> float:
        """Calculate total LLM API cost for all tickets."""
        # TODO: Aggregate from agent_sessions table
        return 0.0

    async def _check_budget_exceeded(self, goal_id: str) -> bool:
        """Check if spending exceeded budget."""
        # TODO: Check against cost_budget table
        return False

    async def _generate_rollback_plan(self, goal_id: str) -> Dict[str, Any]:
        """Generate rollback plan for all changes."""
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.goal_id == goal_id)
            .where(Ticket.state == TicketState.DONE.value)
        )
        tickets = list(result.scalars().all())

        steps = []

        # Step 1: Git revert for all merged changes
        if tickets:
            steps.append({
                "order": 1,
                "type": "git",
                "description": f"Revert all commits for {len(tickets)} tickets",
                "command": "git log --grep='ticket_id' --oneline | awk '{print $1}' | xargs git revert --no-commit",
                "is_automated": True,
                "risk": "low"
            })

        # Step 2: Check for database migrations
        has_migrations = False  # TODO: Detect if any ticket modified migrations
        if has_migrations:
            steps.append({
                "order": 2,
                "type": "migration",
                "description": "Rollback database migrations",
                "command": "alembic downgrade -1",
                "is_automated": False,
                "risk": "high"
            })

        # Step 3: Cache invalidation
        steps.append({
            "order": 3,
            "type": "cache",
            "description": "Clear application caches",
            "command": "redis-cli FLUSHDB",
            "is_automated": True,
            "risk": "low"
        })

        # Assess overall risk
        risk_level = "high" if has_migrations else "low"

        return {
            "steps": steps,
            "risk_level": risk_level,
            "estimated_time": "5-10 minutes",
            "requires_human": any(s["risk"] == "high" for s in steps)
        }

    async def update_manual_check(
        self,
        checklist_id: str,
        check_name: str,
        value: bool
    ) -> MergeChecklist:
        """Update a manual checklist item.

        Args:
            checklist_id: Checklist ID
            check_name: Name of check (code_reviewed, no_sensitive_data, etc.)
            value: New value

        Returns:
            Updated checklist
        """
        result = await self.db.execute(
            select(MergeChecklist).where(MergeChecklist.id == checklist_id)
        )
        checklist = result.scalar_one_or_none()

        if not checklist:
            raise ResourceNotFoundError("MergeChecklist", checklist_id)

        # Update the field
        if hasattr(checklist, check_name):
            setattr(checklist, check_name, value)
        else:
            raise ValueError(f"Unknown check: {check_name}")

        # Recalculate ready status
        checklist.ready_to_merge = checklist.is_ready_to_merge()

        await self.db.flush()
        await self.db.refresh(checklist)

        return checklist

    async def get_checklist_by_goal(self, goal_id: str) -> MergeChecklist | None:
        """Get checklist for a goal."""
        result = await self.db.execute(
            select(MergeChecklist)
            .where(MergeChecklist.goal_id == goal_id)
            .options(selectinload(MergeChecklist.goal))
        )
        return result.scalar_one_or_none()
