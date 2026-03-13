"""Pydantic schemas for Workspace API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceResponse(BaseModel):
    """Response model for workspace information."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_id: str
    worktree_path: str
    branch_name: str
    created_at: datetime
    cleaned_up_at: datetime | None = None
    is_active: bool
