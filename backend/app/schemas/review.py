"""Pydantic schemas for Review entities (comments and summaries)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AuthorType(str, Enum):
    """Enum representing the type of author for a review comment."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class ReviewDecision(str, Enum):
    """Enum representing the review decision."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


# Review Comment Schemas


class ReviewCommentCreate(BaseModel):
    """Schema for creating a review comment."""

    file_path: str = Field(..., min_length=1, max_length=500)
    line_number: int = Field(..., ge=1)
    body: str = Field(..., min_length=1)
    author_type: AuthorType = Field(default=AuthorType.HUMAN)
    # Optional: client can provide hunk_header for anchor calculation
    hunk_header: str | None = Field(
        None, description="Diff hunk header (e.g., '@@ -10,5 +10,7 @@') for anchor stability"
    )
    line_content: str | None = Field(
        None, description="Content of the line being commented on for anchor stability"
    )


class ReviewCommentResponse(BaseModel):
    """Schema for review comment response."""

    id: str
    revision_id: str
    file_path: str
    line_number: int
    anchor: str
    body: str
    author_type: AuthorType
    resolved: bool
    created_at: datetime
    line_content: str | None = None

    model_config = {"from_attributes": True}


class ReviewCommentListResponse(BaseModel):
    """Schema for list of review comments."""

    comments: list[ReviewCommentResponse]
    total: int
    unresolved_count: int


# Review Summary Schemas


class ReviewSubmit(BaseModel):
    """Schema for submitting a review decision."""

    decision: ReviewDecision
    summary: str = Field(default="", description="High-level review feedback (optional)")
    auto_run_fix: bool = Field(
        default=True,
        description="If changes_requested, automatically trigger new agent execution",
    )
    create_pr: bool = Field(
        default=False,
        description="If approved, create a GitHub PR instead of merging directly to main",
    )


class ReviewSummaryResponse(BaseModel):
    """Schema for review summary response."""

    id: str
    revision_id: str
    decision: ReviewDecision
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Feedback Bundle Schema


class FeedbackComment(BaseModel):
    """Schema for a comment in the feedback bundle."""

    file_path: str
    line_number: int
    anchor: str
    body: str
    line_content: str | None = Field(
        default=None,
        description="Content of the line being commented on, helps agent locate the issue",
    )
    orphaned: bool = Field(
        default=False,
        description="True if this comment's anchor cannot be found in the current diff",
    )


class FeedbackBundle(BaseModel):
    """Schema for the feedback bundle sent to the agent.

    This is the structured feedback that gets injected into the agent prompt
    when creating a new revision after changes are requested.
    """

    ticket_id: str
    revision_id: str
    revision_number: int
    decision: str
    summary: str
    comments: list[FeedbackComment]
    orphaned_comment_count: int = Field(
        default=0,
        description="Number of comments that could not be anchored to the current diff",
    )

