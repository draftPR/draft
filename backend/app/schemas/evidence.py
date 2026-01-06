"""Pydantic schemas for Evidence entity."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    """Enum representing the kind of evidence."""

    COMMAND_LOG = "command_log"
    TEST_REPORT = "test_report"


class EvidenceResponse(BaseModel):
    """Schema for evidence response."""

    id: str
    ticket_id: str
    job_id: str
    kind: EvidenceKind
    command: str
    exit_code: int
    stdout_path: str | None
    stderr_path: str | None
    created_at: datetime
    succeeded: bool = Field(description="Whether the command succeeded (exit_code == 0)")

    model_config = {"from_attributes": True}


class EvidenceDetailResponse(EvidenceResponse):
    """Schema for detailed evidence response including stdout/stderr content."""

    stdout: str | None = Field(None, description="Content of stdout (if available)")
    stderr: str | None = Field(None, description="Content of stderr (if available)")


class EvidenceListResponse(BaseModel):
    """Schema for list of evidence records."""

    evidence: list[EvidenceResponse]
    total: int

