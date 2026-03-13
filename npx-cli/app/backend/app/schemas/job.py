"""Pydantic schemas for Job entity."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobKind(StrEnum):
    """Enum representing the kind of job."""

    EXECUTE = "execute"
    VERIFY = "verify"
    RESUME = "resume"


class JobStatus(StrEnum):
    """Enum representing the status of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class JobResponse(BaseModel):
    """Schema for job response."""

    id: str
    ticket_id: str
    kind: JobKind
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    log_path: str | None = None

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    """Schema for detailed job response including logs."""

    logs: str | None = Field(None, description="Job log content")


class JobListResponse(BaseModel):
    """Schema for list of jobs response."""

    jobs: list[JobResponse]
    total: int


class JobCreateResponse(JobResponse):
    """Schema for job creation response."""

    celery_task_id: str | None = None


class CancelJobResponse(BaseModel):
    """Schema for job cancellation response."""

    id: str
    status: JobStatus
    message: str


class QueuedJobResponse(BaseModel):
    """Schema for a job in the queue with ticket info."""

    id: str
    ticket_id: str
    ticket_title: str
    kind: JobKind
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    queue_position: int | None = Field(
        None, description="Position in queue (1-based, None if running)"
    )

    model_config = {"from_attributes": True}


class QueueStatusResponse(BaseModel):
    """Schema for queue status response."""

    running: list[QueuedJobResponse] = Field(
        default_factory=list, description="Currently running jobs"
    )
    queued: list[QueuedJobResponse] = Field(
        default_factory=list, description="Jobs waiting in queue (ordered)"
    )
    total_running: int = 0
    total_queued: int = 0
