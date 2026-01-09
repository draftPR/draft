"""Board schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    """Schema for creating a new board."""

    name: str = Field(..., min_length=1, max_length=255, description="Board name")
    description: str | None = Field(None, description="Optional description")
    repo_root: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Absolute path to repository root",
    )
    default_branch: str | None = Field(
        None,
        max_length=255,
        description="Default branch (e.g., main, master)",
    )


class BoardUpdate(BaseModel):
    """Schema for updating a board."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    default_branch: str | None = None
    
    class Config:
        extra = "ignore"


class BoardResponse(BaseModel):
    """Schema for board API response."""

    id: str
    name: str
    description: str | None
    repo_root: str
    default_branch: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BoardListResponse(BaseModel):
    """Schema for list of boards."""

    boards: list[BoardResponse]
    total: int


