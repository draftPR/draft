"""DraftClient — the main entry point for the Draft SDK."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from ._http import HttpClient
from .boards import BoardsResource
from .exceptions import DraftTimeoutError
from .goals import GoalsResource
from .jobs import JobsResource
from .models import GoalResult, Ticket
from .planner import PlannerResource
from .revisions import RevisionsResource
from .tickets import TicketsResource

logger = logging.getLogger("draft_sdk")

_TERMINAL_TICKET_STATES = {"done", "abandoned"}
_ACTIVE_TICKET_STATES = {"executing", "verifying"}


class DraftClient:
    """Python client for the Draft API.

    Usage::

        from draft_sdk import DraftClient

        client = DraftClient("http://localhost:8000")
        result = client.run_goal("Add dark mode", auto_approve=True, wait=True)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: str | None = None,
        timeout: float = 600.0,
        board_id: str | None = None,
    ):
        self._http = HttpClient(base_url=base_url, token=token, timeout=timeout)
        self._default_board_id = board_id

        # Resource namespaces
        self.boards = BoardsResource(self._http)
        self.goals = GoalsResource(self._http)
        self.tickets = TicketsResource(self._http)
        self.jobs = JobsResource(self._http)
        self.revisions = RevisionsResource(self._http)
        self.planner = PlannerResource(self._http)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> DraftClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- Convenience ----------------------------------------------------------

    def health(self) -> dict:
        """Check server health."""
        return self._http.get("/health")

    def version(self) -> dict:
        """Get server version info."""
        return self._http.get("/version")

    # -- High-level orchestration --------------------------------------------

    def run_goal(
        self,
        title: str,
        description: str | None = None,
        board_id: str | None = None,
        auto_approve: bool = True,
        wait: bool = True,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
        on_progress: Callable[[str, Any], None] | None = None,
    ) -> GoalResult:
        """Create a goal and run it through the full lifecycle.

        Args:
            title: Goal title (natural language description).
            description: Optional detailed description.
            board_id: Board to create the goal on (uses default if not set).
            auto_approve: Auto-approve generated tickets (PROPOSED → PLANNED).
            wait: Block until all tickets reach a terminal state.
            poll_interval: Seconds between status polls when waiting.
            timeout: Max seconds to wait for completion.
            on_progress: Optional callback ``(event_type, data) -> None``.

        Returns:
            GoalResult with final status and ticket list.
        """
        bid = board_id or self._default_board_id
        if not bid:
            # Auto-discover first board
            boards = self.boards.list()
            if boards:
                bid = boards[0].id

        # 1. Create goal
        goal = self.goals.create(
            title=title,
            description=description,
            board_id=bid,
            autonomy_enabled=auto_approve,
            auto_approve_tickets=auto_approve,
        )
        _emit(on_progress, "goal_created", {"goal_id": goal.id, "title": goal.title})
        logger.info("Created goal %s: %s", goal.id, goal.title)

        # 2. Generate tickets
        tickets = self.goals.generate_tickets(goal.id)
        _emit(on_progress, "tickets_generated", {"count": len(tickets)})
        logger.info("Generated %d tickets", len(tickets))

        if not tickets:
            return GoalResult(goal=goal, status="no_tickets", tickets=[])

        # 3. Approve tickets
        if auto_approve:
            proposed = [t.id for t in tickets if t.state == "proposed"]
            if proposed:
                self.tickets.accept(proposed)
                _emit(on_progress, "tickets_approved", {"count": len(proposed)})
                logger.info("Approved %d tickets", len(proposed))

        if not wait:
            # Fire-and-forget: trigger execution for first planned ticket
            planned = self.tickets.list(goal_id=goal.id, state="planned")
            if planned:
                self.tickets.execute(planned[0].id)
            return GoalResult(goal=goal, status="executing", tickets=tickets)

        # 4. Wait for completion
        deadline = time.monotonic() + timeout
        while True:
            current = self.tickets.list(goal_id=goal.id)
            states = {t.state for t in current}
            _emit(on_progress, "poll", {
                "states": {s: sum(1 for t in current if t.state == s) for s in states}
            })

            # All tickets in terminal states?
            if all(t.state in _TERMINAL_TICKET_STATES for t in current):
                break

            # Any tickets that need human review? Approve if auto_approve
            needs_human = [t for t in current if t.state == "needs_human"]
            if auto_approve and needs_human:
                for t in needs_human:
                    revs = self.revisions.list(t.id)
                    if revs:
                        self.revisions.review(revs[0].id, decision="approved")
                        _emit(on_progress, "revision_approved", {"ticket_id": t.id})
                        logger.info("Auto-approved revision for ticket %s", t.id)

            # Any planned tickets not yet executing? Kick them off
            planned = [t for t in current if t.state == "planned"]
            active = [t for t in current if t.state in _ACTIVE_TICKET_STATES]
            if planned and not active:
                self.tickets.execute(planned[0].id)
                _emit(on_progress, "ticket_executing", {"ticket_id": planned[0].id})

            if time.monotonic() > deadline:
                raise DraftTimeoutError(f"Goal {goal.id} not complete after {timeout}s")

            time.sleep(poll_interval)

        # 5. Return result
        final = self.tickets.list(goal_id=goal.id)
        all_done = all(t.state == "done" for t in final)
        has_blocked = any(t.state == "blocked" for t in final)
        status = "completed" if all_done else ("blocked" if has_blocked else "partial")

        _emit(on_progress, "complete", {"status": status})
        logger.info("Goal %s finished with status: %s", goal.id, status)
        return GoalResult(goal=goal, status=status, tickets=final)


def _emit(callback: Callable | None, event: str, data: Any) -> None:
    if callback:
        try:
            callback(event, data)
        except Exception:
            logger.debug("Progress callback error for event %s", event, exc_info=True)
