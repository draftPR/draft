"""Pydantic schemas for Goal entity."""

from datetime import datetime

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    """Schema for creating a new goal."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class GoalResponse(BaseModel):
    """Schema for goal response."""

    id: str
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoalListResponse(BaseModel):
    """Schema for list of goals response."""

    goals: list[GoalResponse]
    total: int
