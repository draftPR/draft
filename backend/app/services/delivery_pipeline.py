"""End-to-end autonomous delivery pipeline orchestration.

This service orchestrates the complete workflow:
Goal → Tickets → Execute → Verify → PR → Review → Merge
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import SmartKanbanError
from app.models.goal import Goal
from app.models.job import Job
from app.models.ticket import Ticket
from app.services.reliability_wrapper import ReliabilityWrapper, RetryConfig
from app.services.safe_autopilot import (
    GateAction,
    SafeAutopilot,
    create_default_autopilot,
)
from app.state_machine import JobStatus, TicketState

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the full delivery pipeline."""
    status: str  # "ready_for_merge", "blocked", "in_progress"
    reason: str | None = None
    tickets_completed: list[str] = None
    tickets_blocked: list[str] = None
    pr_url: str | None = None
    checklist_id: str | None = None
    evidence: dict[str, Any] = None
    total_cost_usd: float = 0.0

    def __post_init__(self):
        if self.tickets_completed is None:
            self.tickets_completed = []
        if self.tickets_blocked is None:
            self.tickets_blocked = []
        if self.evidence is None:
            self.evidence = {}


class PipelineError(SmartKanbanError):
    """Error during pipeline execution."""
    pass


class DeliveryPipeline:
    """
    Orchestrates the complete autonomous delivery workflow.

    This is the "autopilot" that takes a goal and delivers merge-ready code.
    """

    def __init__(
        self,
        db: AsyncSession,
        retry_config: RetryConfig | None = None,
        autopilot: SafeAutopilot | None = None
    ):
        self.db = db
        self.reliability_wrapper = ReliabilityWrapper(
            db=db,
            retry_config=retry_config or RetryConfig(max_retries=3)
        )
        self.autopilot = autopilot or create_default_autopilot(db)

    async def run_full_pipeline(
        self,
        goal_id: str,
        auto_approve: bool = False,
        dry_run: bool = False
    ) -> PipelineResult:
        """Run the complete pipeline from goal to merge-ready state.

        Args:
            goal_id: The goal to deliver
            auto_approve: If True, automatically approve all steps (YOLO mode)
            dry_run: If True, simulate but don't actually execute

        Returns:
            PipelineResult with status and details
        """
        logger.info(f"Starting delivery pipeline for goal {goal_id} (auto_approve={auto_approve}, dry_run={dry_run})")

        try:
            # Stage 1: Validate goal exists and get tickets
            goal, tickets = await self._validate_and_load(goal_id)

            if not tickets:
                return PipelineResult(
                    status="blocked",
                    reason="No tickets found for this goal. Generate tickets first."
                )

            # Stage 2: Topologically sort tickets by dependencies
            sorted_tickets = self._topological_sort(tickets)
            logger.info(f"Execution order: {[t.id for t in sorted_tickets]}")

            # Stage 3: Execute tickets in order with safety gates
            completed = []
            blocked = []

            for ticket in sorted_tickets:
                if dry_run:
                    logger.info(f"[DRY RUN] Would execute ticket {ticket.id}: {ticket.title}")
                    completed.append(ticket.id)
                    continue

                # Execute ticket
                result = await self._execute_with_retry(ticket, max_retries=2)

                if result["status"] == "success":
                    completed.append(ticket.id)

                    # Check safety gates after successful execution
                    can_continue, gate_results = await self.autopilot.should_continue(ticket)

                    if not can_continue:
                        # Find blocking or pausing gates
                        blocking_gates = [
                            r for r in gate_results
                            if not r.passed and r.action in [GateAction.BLOCK, GateAction.PAUSE]
                        ]

                        reasons = [f"{r.gate_name}: {r.reason}" for r in blocking_gates]

                        logger.warning(
                            f"Safety gates triggered for ticket {ticket.id}: {', '.join(reasons)}"
                        )

                        if not auto_approve:
                            return PipelineResult(
                                status="blocked",
                                reason=f"Safety gates failed: {', '.join(reasons)}",
                                tickets_completed=completed,
                                tickets_blocked=[ticket.id]
                            )

                    # Log any alert-level gate failures
                    alert_gates = [
                        r for r in gate_results
                        if not r.passed and r.action == GateAction.ALERT
                    ]
                    for alert in alert_gates:
                        logger.warning(f"Gate alert for ticket {ticket.id}: {alert.reason}")

                else:
                    blocked.append(ticket.id)
                    # If one ticket fails and not auto_approve, stop here
                    if not auto_approve:
                        return PipelineResult(
                            status="blocked",
                            reason=f"Ticket {ticket.id} failed: {result.get('reason')}",
                            tickets_completed=completed,
                            tickets_blocked=blocked
                        )

            # Stage 4: Verify all tickets passed
            if not dry_run:
                verification = await self._verify_all(tickets)
                if not verification["passed"]:
                    return PipelineResult(
                        status="blocked",
                        reason=f"Verification failed: {verification['failures']}",
                        tickets_completed=completed,
                        tickets_blocked=blocked
                    )

            # Stage 5: Collect evidence for review
            evidence = await self._collect_evidence(tickets)

            # Stage 6: Calculate total cost
            total_cost = await self._calculate_total_cost(goal_id)

            return PipelineResult(
                status="ready_for_merge",
                tickets_completed=completed,
                evidence=evidence,
                total_cost_usd=total_cost
            )

        except Exception as e:
            logger.exception(f"Pipeline failed for goal {goal_id}")
            raise PipelineError(f"Pipeline execution failed: {str(e)}") from e

    async def _validate_and_load(self, goal_id: str) -> tuple[Goal, list[Ticket]]:
        """Validate goal exists and load all its tickets."""
        result = await self.db.execute(
            select(Goal)
            .where(Goal.id == goal_id)
            .options(selectinload(Goal.tickets))
        )
        goal = result.scalar_one_or_none()

        if not goal:
            raise PipelineError(f"Goal {goal_id} not found")

        # Get all tickets for this goal
        ticket_result = await self.db.execute(
            select(Ticket)
            .where(Ticket.goal_id == goal_id)
            .options(selectinload(Ticket.jobs))
        )
        tickets = list(ticket_result.scalars().all())

        return goal, tickets

    def _topological_sort(self, tickets: list[Ticket]) -> list[Ticket]:
        """Sort tickets by dependencies (topological order).

        Tickets with no dependencies come first.
        Blocked tickets come after their blockers.
        """
        # Build dependency graph
        ticket_map = {t.id: t for t in tickets}
        in_degree = {t.id: 0 for t in tickets}
        graph = {t.id: [] for t in tickets}

        for ticket in tickets:
            if ticket.blocked_by_ticket_id:
                if ticket.blocked_by_ticket_id in graph:
                    graph[ticket.blocked_by_ticket_id].append(ticket.id)
                    in_degree[ticket.id] += 1

        # Kahn's algorithm for topological sort
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        sorted_ids = []

        while queue:
            # Sort by priority within the queue
            queue.sort(key=lambda tid: ticket_map[tid].priority or 0, reverse=True)
            current = queue.pop(0)
            sorted_ids.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if len(sorted_ids) != len(tickets):
            logger.warning("Cycle detected in ticket dependencies, using original order")
            return tickets

        return [ticket_map[tid] for tid in sorted_ids]

    async def _execute_with_retry(
        self,
        ticket: Ticket,
        max_retries: int = 2
    ) -> dict[str, Any]:
        """Execute a ticket with automatic retry, checkpointing, and recovery.

        Uses ReliabilityWrapper for robust execution with:
        - Exponential backoff retry
        - Checkpointing for resume capability
        - Intelligent error classification

        Returns:
            Dict with status and reason
        """
        from app.services.job_service import JobService

        # Check if ticket is in correct state
        if ticket.state not in [TicketState.PLANNED.value, TicketState.BLOCKED.value]:
            return {
                "status": "skipped",
                "reason": f"Ticket in state {ticket.state}, not ready for execution"
            }

        job_service = JobService(self.db)

        async def execute_ticket_with_job():
            """Inner function that creates job and executes ticket."""
            # Create execution job
            job = await job_service.create_job(
                ticket_id=ticket.id,
                job_type="execute",
                board_id=ticket.board_id
            )

            logger.info(f"Executing ticket {ticket.id} with job {job.id}")

            # TODO: Actually call the Celery task and wait for completion
            # For now, just mark as success if job created

            return {
                "status": "success",
                "job_id": job.id
            }

        try:
            # Execute with reliability wrapper (automatic retry, checkpointing)
            result = await self.reliability_wrapper.execute_with_reliability(
                func=execute_ticket_with_job,
                ticket_id=ticket.id,
                job_id=None,  # Job created inside function
                checkpoint_key=f"pipeline:execute:{ticket.id}"
            )

            return result

        except Exception as e:
            logger.error(f"Ticket {ticket.id} execution failed after all retries: {e}")
            return {
                "status": "failed",
                "reason": str(e)
            }

    async def _verify_all(self, tickets: list[Ticket]) -> dict[str, Any]:
        """Run verification for all tickets and aggregate results.

        Returns:
            Dict with passed flag and list of failures
        """
        from app.services.job_service import JobService

        JobService(self.db)
        failures = []

        for ticket in tickets:
            # Get most recent verification job
            result = await self.db.execute(
                select(Job)
                .where(Job.ticket_id == ticket.id)
                .where(Job.job_type == "verify")
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            verify_job = result.scalar_one_or_none()

            if not verify_job:
                failures.append(f"Ticket {ticket.id}: No verification run")
                continue

            if verify_job.status != JobStatus.SUCCEEDED.value:
                failures.append(f"Ticket {ticket.id}: Verification {verify_job.status}")

        return {
            "passed": len(failures) == 0,
            "failures": failures
        }

    async def _collect_evidence(self, tickets: list[Ticket]) -> dict[str, Any]:
        """Collect all evidence (diffs, tests, logs) for tickets.

        Returns:
            Dict with evidence summary
        """
        evidence = {
            "total_tickets": len(tickets),
            "files_changed": [],
            "tests_run": 0,
            "tests_passed": 0,
            "diffs": []
        }

        for ticket in tickets:
            # Get all jobs for this ticket
            result = await self.db.execute(
                select(Job)
                .where(Job.ticket_id == ticket.id)
                .options(selectinload(Job.evidence))
            )
            jobs = list(result.scalars().all())

            for job in jobs:
                if job.evidence:
                    evidence["diffs"].extend([
                        {
                            "ticket_id": ticket.id,
                            "job_id": job.id,
                            "evidence_id": e.id,
                            "type": e.evidence_type
                        }
                        for e in job.evidence
                    ])

        return evidence

    async def _calculate_total_cost(self, goal_id: str) -> float:
        """Calculate total LLM API cost for all tickets in goal.

        Returns:
            Total cost in USD
        """
        # TODO: Implement cost tracking aggregation
        # For now, return 0
        return 0.0


async def get_pipeline_status(db: AsyncSession, goal_id: str) -> dict[str, Any]:
    """Get the current status of the delivery pipeline for a goal.

    Returns:
        Dict with pipeline status, progress, and blocking issues
    """
    result = await db.execute(
        select(Ticket)
        .where(Ticket.goal_id == goal_id)
    )
    tickets = list(result.scalars().all())

    if not tickets:
        return {
            "status": "not_started",
            "reason": "No tickets generated yet"
        }

    state_counts = {}
    for ticket in tickets:
        state = ticket.state
        state_counts[state] = state_counts.get(state, 0) + 1

    total = len(tickets)
    completed = state_counts.get(TicketState.DONE.value, 0)
    blocked = state_counts.get(TicketState.BLOCKED.value, 0)
    executing = state_counts.get(TicketState.EXECUTING.value, 0) + state_counts.get(TicketState.VERIFYING.value, 0)

    if blocked > 0:
        status = "blocked"
    elif executing > 0:
        status = "in_progress"
    elif completed == total:
        status = "ready_for_merge"
    else:
        status = "ready_to_execute"

    return {
        "status": status,
        "total_tickets": total,
        "completed": completed,
        "blocked": blocked,
        "executing": executing,
        "progress_percent": int((completed / total) * 100) if total > 0 else 0,
        "state_breakdown": state_counts
    }
