"""Planner resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._http import HttpClient


class PlannerResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def status(self, health_check: bool = False) -> dict:
        """Get planner status, config, and last tick stats."""
        return self._http.get("/planner/status", health_check=str(health_check).lower())

    def tick(self) -> dict:
        """Run a single planner decision cycle."""
        return self._http.post("/planner/tick")

    def start(
        self,
        max_duration: int = 3600,
        poll_interval: int = 5,
    ) -> dict:
        """Start autopilot: queue all PLANNED tickets, poll until done."""
        return self._http.post(
            "/planner/start",
            json={
                "max_duration_seconds": max_duration,
                "poll_interval_seconds": poll_interval,
            },
        )

    def release_lock(self) -> dict:
        """Emergency unlock of the planner lock."""
        return self._http.post("/planner/release-lock")
