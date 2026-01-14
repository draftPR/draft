"""Pydantic schemas for Revision entity."""

from datetime import datetime

from pydantic import BaseModel, Field

# Import RevisionStatus from models to avoid duplication
from app.models.revision import RevisionStatus


class RevisionResponse(BaseModel):
    """Schema for revision response."""

    id: str
    ticket_id: str
    job_id: str
    number: int
    status: RevisionStatus
    diff_stat_evidence_id: str | None
    diff_patch_evidence_id: str | None
    created_at: datetime
    unresolved_comment_count: int = Field(
        default=0, description="Number of unresolved review comments"
    )

    model_config = {"from_attributes": True}


class RevisionDetailResponse(RevisionResponse):
    """Schema for detailed revision response with diff content."""

    diff_stat: str | None = Field(None, description="Git diff stat output")
    diff_patch: str | None = Field(None, description="Full git diff patch")


class RevisionListResponse(BaseModel):
    """Schema for list of revisions."""

    revisions: list[RevisionResponse]
    total: int


class RevisionDiffResponse(BaseModel):
    """Schema for revision diff content (both stat and patch - heavyweight)."""

    revision_id: str
    diff_stat: str | None = Field(None, description="Git diff stat output")
    diff_patch: str | None = Field(None, description="Full git diff patch")
    files: list["DiffFile"] = Field(default_factory=list, description="Parsed diff files")


class DiffSummaryResponse(BaseModel):
    """Schema for lightweight diff summary (stat + file list only).

    Use this endpoint for initial load - no heavy patch content.
    """

    revision_id: str
    diff_stat: str | None = Field(None, description="Git diff stat output")
    files: list["DiffFile"] = Field(default_factory=list, description="Parsed diff files")


class DiffPatchResponse(BaseModel):
    """Schema for heavyweight diff patch content.

    Only fetch this when user actually opens the diff viewer.
    """

    revision_id: str
    diff_patch: str | None = Field(None, description="Full git diff patch")


class DiffFile(BaseModel):
    """Schema for a single file in the diff."""

    path: str
    old_path: str | None = None
    additions: int = 0
    deletions: int = 0
    status: str = Field(
        default="modified",
        description="File status: added, deleted, modified, renamed",
    )


class TimelineEvent(BaseModel):
    """Schema for a single event in the revision timeline."""

    id: str
    event_type: str = Field(
        description="Event type: revision_created, comment_added, review_submitted, job_queued, job_completed"
    )
    actor: str = Field(description="Who triggered this event (human, agent, system)")
    message: str = Field(description="Human-readable description of the event")
    created_at: datetime
    metadata: dict | None = Field(default=None, description="Additional event-specific data")


class RevisionTimelineResponse(BaseModel):
    """Schema for revision timeline (audit trail of events)."""

    revision_id: str
    events: list[TimelineEvent]


# For forward reference
RevisionDiffResponse.model_rebuild()
DiffSummaryResponse.model_rebuild()

