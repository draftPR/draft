"""Pydantic schemas for Job entity."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobKind(str, Enum):
    """Enum representing the kind of job."""

    EXECUTE = "execute"
    VERIFY = "verify"


class JobStatus(str, Enum):
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
