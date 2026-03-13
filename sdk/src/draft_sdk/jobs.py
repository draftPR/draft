"""Jobs resource."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from .exceptions import DraftTimeoutError
from .models import Job

if TYPE_CHECKING:
    from ._http import HttpClient

_TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class JobsResource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def get(self, job_id: str) -> Job:
        return Job.model_validate(self._http.get(f"/jobs/{job_id}"))

    def list(
        self,
        ticket_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> list[Job]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if ticket_id:
            params["ticket_id"] = ticket_id
        if status:
            params["status"] = status
        if kind:
            params["kind"] = kind
        data = self._http.get("/jobs", **params)
        items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
        return [Job.model_validate(j) for j in items]

    def logs(self, job_id: str) -> str:
        """Get raw plain-text logs for a job."""
        return self._http.get_text(f"/jobs/{job_id}/logs")

    def cancel(self, job_id: str) -> Job:
        return Job.model_validate(self._http.post(f"/jobs/{job_id}/cancel"))

    def wait(
        self,
        job_id: str,
        poll_interval: float = 3.0,
        timeout: float = 600.0,
    ) -> Job:
        """Poll until the job reaches a terminal state."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.get(job_id)
            if job.status in _TERMINAL_STATUSES:
                return job
            if time.monotonic() > deadline:
                raise DraftTimeoutError(
                    f"Job {job_id} still in '{job.status}' after {timeout}s"
                )
            time.sleep(poll_interval)

    def queue_status(self) -> dict:
        """Get current running + queued jobs."""
        return self._http.get("/jobs/queue")
