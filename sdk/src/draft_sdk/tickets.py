"""Tickets resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import BulkAcceptResult, Job, Ticket

if TYPE_CHECKING:
    from ._http import HttpClient


class TicketsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get(self, ticket_id: str) -> Ticket:
        return Ticket.model_validate(self._http.get(f"/tickets/{ticket_id}"))

    def list(
        self,
        goal_id: str | None = None,
        board_id: str | None = None,
        state: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> list[Ticket]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if goal_id:
            params["goal_id"] = goal_id
        if board_id:
            params["board_id"] = board_id
        if state:
            params["state"] = state
        data = self._http.get("/tickets", **params)
        items = data if isinstance(data, list) else data.get("tickets", data.get("items", []))
        return [Ticket.model_validate(t) for t in items]

    def create(
        self,
        goal_id: str,
        title: str,
        description: str | None = None,
        priority: int | None = None,
        blocked_by_ticket_id: str | None = None,
    ) -> Ticket:
        body: dict[str, Any] = {"goal_id": goal_id, "title": title}
        if description:
            body["description"] = description
        if priority is not None:
            body["priority"] = priority
        if blocked_by_ticket_id:
            body["blocked_by_ticket_id"] = blocked_by_ticket_id
        return Ticket.model_validate(self._http.post("/tickets", json=body))

    def update(self, ticket_id: str, **kwargs: Any) -> Ticket:
        return Ticket.model_validate(self._http.patch(f"/tickets/{ticket_id}", json=kwargs))

    def transition(self, ticket_id: str, to_state: str, reason: str | None = None) -> Ticket:
        body: dict[str, Any] = {"state": to_state}
        if reason:
            body["reason"] = reason
        return Ticket.model_validate(
            self._http.post(f"/tickets/{ticket_id}/transition", json=body)
        )

    def accept(self, ticket_ids: list[str], queue_first: bool = False) -> BulkAcceptResult:
        """Bulk accept tickets: PROPOSED → PLANNED."""
        body: dict[str, Any] = {"ticket_ids": ticket_ids}
        if queue_first:
            body["queue_first"] = True
        return BulkAcceptResult.model_validate(self._http.post("/tickets/accept", json=body))

    def execute(self, ticket_id: str) -> Job:
        """Enqueue an execute job for a ticket."""
        return Job.model_validate(self._http.post(f"/tickets/{ticket_id}/execute"))

    def verify(self, ticket_id: str) -> Job:
        """Enqueue a verify job for a ticket."""
        return Job.model_validate(self._http.post(f"/tickets/{ticket_id}/verify"))

    def delete(self, ticket_id: str) -> None:
        self._http.delete(f"/tickets/{ticket_id}")

    def events(self, ticket_id: str) -> list[dict]:
        """Get ticket event history."""
        data = self._http.get(f"/tickets/{ticket_id}/events")
        return data if isinstance(data, list) else data.get("events", [])
