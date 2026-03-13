"""Pydantic schemas for Goal entity."""

from datetime import datetime

from pydantic import BaseModel, Field


class AutonomySettings(BaseModel):
    """Schema for autonomy settings on a goal."""

    autonomy_enabled: bool = False
    auto_approve_tickets: bool = False
    auto_approve_revisions: bool = False
    auto_merge: bool = False
    auto_approve_followups: bool = False
    max_auto_approvals: int | None = None


class GoalCreate(BaseModel):
    """Schema for creating a new goal."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    board_id: str | None = Field(
        None,
        description="Board ID to scope this goal to (recommended for multi-board setups)",
    )
    # Autonomy fields (optional at creation)
    autonomy_enabled: bool = False
    auto_approve_tickets: bool = False
    auto_approve_revisions: bool = False
    auto_merge: bool = False
    auto_approve_followups: bool = False
    max_auto_approvals: int | None = None


class GoalUpdate(BaseModel):
    """Schema for updating a goal."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    autonomy_enabled: bool | None = None
    auto_approve_tickets: bool | None = None
    auto_approve_revisions: bool | None = None
    auto_merge: bool | None = None
    auto_approve_followups: bool | None = None
    max_auto_approvals: int | None = None


class GoalResponse(BaseModel):
    """Schema for goal response."""

    id: str
    board_id: str | None = None
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    # Autonomy fields
    autonomy_enabled: bool = False
    auto_approve_tickets: bool = False
    auto_approve_revisions: bool = False
    auto_merge: bool = False
    auto_approve_followups: bool = False
    max_auto_approvals: int | None = None
    auto_approval_count: int = 0

    model_config = {"from_attributes": True}


class GoalListResponse(BaseModel):
    """Schema for list of goals response."""

    goals: list[GoalResponse]
    total: int


class AutonomyStatusResponse(BaseModel):
    """Schema for autonomy status response."""

    goal_id: str
    autonomy_enabled: bool
    auto_approve_tickets: bool
    auto_approve_revisions: bool
    auto_merge: bool
    auto_approve_followups: bool
    max_auto_approvals: int | None
    auto_approval_count: int
    budget_remaining: float | None = None
    safety_checks: list[dict] = Field(default_factory=list)
