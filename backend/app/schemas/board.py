"""Board schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    default_branch: str | None = None
    config: dict | None = Field(None, description="Board-level configuration overrides")


class BoardResponse(BaseModel):
    """Schema for board API response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    repo_root: str
    default_branch: str | None
    created_at: datetime
    updated_at: datetime


class BoardListResponse(BaseModel):
    """Schema for list of boards."""

    boards: list[BoardResponse]
    total: int


class BoardConfigUpdate(BaseModel):
    """Schema for updating board-level configuration overrides."""

    model_config = ConfigDict(extra="ignore")

    config: dict | None = Field(
        None,
        description="Board-level configuration that overrides smartkanban.yaml settings",
    )


class BoardConfigResponse(BaseModel):
    """Schema for board configuration response."""

    board_id: str
    config: dict | None = Field(None, description="Board-level configuration JSON")
    has_overrides: bool = Field(
        default=False,
        description="Whether the board has custom configuration overrides",
    )
