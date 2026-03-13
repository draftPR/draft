"""Goals resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import Goal, GoalProgress, Ticket

if TYPE_CHECKING:
    from ._http import HttpClient


class GoalsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def create(
        self,
        title: str,
        description: str | None = None,
        board_id: str | None = None,
        autonomy_enabled: bool = False,
        auto_approve_tickets: bool = False,
        auto_approve_revisions: bool = False,
        auto_merge: bool = False,
    ) -> Goal:
        body: dict[str, Any] = {"title": title}
        if description:
            body["description"] = description
        if board_id:
            body["board_id"] = board_id
        if autonomy_enabled:
            body["autonomy_enabled"] = True
        if auto_approve_tickets:
            body["auto_approve_tickets"] = True
        if auto_approve_revisions:
            body["auto_approve_revisions"] = True
        if auto_merge:
            body["auto_merge"] = True
        return Goal.model_validate(self._http.post("/goals", json=body))

    def get(self, goal_id: str) -> Goal:
        return Goal.model_validate(self._http.get(f"/goals/{goal_id}"))

    def list(self, board_id: str | None = None, page: int = 1, limit: int = 50) -> list[Goal]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if board_id:
            params["board_id"] = board_id
        data = self._http.get("/goals", **params)
        items = data if isinstance(data, list) else data.get("goals", data.get("items", []))
        return [Goal.model_validate(g) for g in items]

    def update(self, goal_id: str, **kwargs: Any) -> Goal:
        return Goal.model_validate(self._http.patch(f"/goals/{goal_id}", json=kwargs))

    def delete(self, goal_id: str) -> None:
        self._http.delete(f"/goals/{goal_id}")

    def generate_tickets(self, goal_id: str) -> list[Ticket]:
        """Trigger AI ticket generation and return created tickets."""
        data = self._http.post(f"/goals/{goal_id}/generate-tickets")
        items = data if isinstance(data, list) else data.get("tickets", [])
        return [Ticket.model_validate(t) for t in items]

    def progress(self, goal_id: str) -> GoalProgress:
        """Get goal progress summary (ticket state breakdown)."""
        return GoalProgress.model_validate(self._http.get(f"/goals/{goal_id}/progress"))

    def update_autonomy(
        self,
        goal_id: str,
        autonomy_enabled: bool | None = None,
        auto_approve_tickets: bool | None = None,
        auto_approve_revisions: bool | None = None,
        auto_merge: bool | None = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if autonomy_enabled is not None:
            body["autonomy_enabled"] = autonomy_enabled
        if auto_approve_tickets is not None:
            body["auto_approve_tickets"] = auto_approve_tickets
        if auto_approve_revisions is not None:
            body["auto_approve_revisions"] = auto_approve_revisions
        if auto_merge is not None:
            body["auto_merge"] = auto_merge
        return self._http.patch(f"/goals/{goal_id}/autonomy", json=body)
