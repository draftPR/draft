"""Pydantic schemas for Goal entity."""

from datetime import datetime

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    """Schema for creating a new goal."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    board_id: str | None = Field(
        None,
        description="Board ID to scope this goal to (recommended for multi-board setups)",
    )


class GoalResponse(BaseModel):
    """Schema for goal response."""

    id: str
    board_id: str | None = None
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoalListResponse(BaseModel):
    """Schema for list of goals response."""

    goals: list[GoalResponse]
    total: int
