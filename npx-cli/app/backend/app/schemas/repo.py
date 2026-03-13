"""Pydantic schemas for Repo and BoardRepo models."""

from datetime import datetime

from pydantic import BaseModel, Field

# ============================================================================
# Repo schemas
# ============================================================================


class RepoBase(BaseModel):
    """Base schema for Repo."""

    path: str = Field(..., description="Filesystem path to git repository")
    name: str = Field(..., description="Repository name (derived from path)")
    display_name: str = Field(..., description="User-friendly display name")
    setup_script: str | None = Field(None, description="Optional setup script")
    cleanup_script: str | None = Field(None, description="Optional cleanup script")
    dev_server_script: str | None = Field(
        None, description="Optional dev server script"
    )
    default_branch: str | None = Field(None, description="Default git branch")
    remote_url: str | None = Field(None, description="Git remote URL")


class RepoCreate(BaseModel):
    """Schema for creating a new repo."""

    path: str = Field(..., description="Filesystem path to git repository")
    display_name: str | None = Field(
        None, description="Optional display name (defaults to repo name)"
    )
    setup_script: str | None = Field(None, description="Optional setup script")
    cleanup_script: str | None = Field(None, description="Optional cleanup script")
    dev_server_script: str | None = Field(
        None, description="Optional dev server script"
    )


class RepoUpdate(BaseModel):
    """Schema for updating a repo."""

    display_name: str | None = Field(None, description="User-friendly display name")
    setup_script: str | None = Field(None, description="Optional setup script")
    cleanup_script: str | None = Field(None, description="Optional cleanup script")
    dev_server_script: str | None = Field(
        None, description="Optional dev server script"
    )


class RepoResponse(RepoBase):
    """Schema for repo API responses."""

    id: str = Field(..., description="Repo UUID")
    created_at: datetime = Field(..., description="When repo was registered")
    updated_at: datetime = Field(..., description="When repo was last updated")

    class Config:
        from_attributes = True


class RepoListResponse(BaseModel):
    """Schema for repo list API response."""

    repos: list[RepoResponse] = Field(..., description="List of repos")
    total: int = Field(..., description="Total number of repos")


# ============================================================================
# Discovery schemas
# ============================================================================


class DiscoveredRepoResponse(BaseModel):
    """Schema for discovered repo (not yet registered)."""

    path: str = Field(..., description="Filesystem path to git repository")
    name: str = Field(..., description="Repository name")
    display_name: str = Field(..., description="Display name")
    default_branch: str | None = Field(None, description="Default git branch")
    remote_url: str | None = Field(None, description="Git remote URL")
    is_valid: bool = Field(..., description="Whether repo is valid")
    error_message: str | None = Field(None, description="Error message if invalid")


class DiscoverReposRequest(BaseModel):
    """Schema for repo discovery request."""

    search_paths: list[str] = Field(
        ..., description="Paths to scan for git repositories"
    )
    max_depth: int = Field(
        3, description="Maximum directory depth to scan", ge=1, le=10
    )
    exclude_patterns: list[str] | None = Field(
        None, description="Additional patterns to exclude"
    )


class DiscoverReposResponse(BaseModel):
    """Schema for repo discovery response."""

    discovered: list[DiscoveredRepoResponse] = Field(
        ..., description="List of discovered repos"
    )
    total: int = Field(..., description="Total repos found")


class ValidateRepoRequest(BaseModel):
    """Schema for repo validation request."""

    path: str = Field(..., description="Path to validate as git repository")


class ValidateRepoResponse(BaseModel):
    """Schema for repo validation response."""

    is_valid: bool = Field(..., description="Whether path is valid git repo")
    path: str = Field(..., description="Normalized path")
    error_message: str | None = Field(None, description="Error message if invalid")
    metadata: DiscoveredRepoResponse | None = Field(
        None, description="Repo metadata if valid"
    )


# ============================================================================
# BoardRepo schemas
# ============================================================================


class BoardRepoBase(BaseModel):
    """Base schema for BoardRepo junction."""

    board_id: str = Field(..., description="Board UUID")
    repo_id: str = Field(..., description="Repo UUID")
    is_primary: bool = Field(False, description="Whether this is the primary repo")
    custom_setup_script: str | None = Field(
        None, description="Per-board setup script override"
    )
    custom_cleanup_script: str | None = Field(
        None, description="Per-board cleanup script override"
    )


class BoardRepoCreate(BaseModel):
    """Schema for adding a repo to a board."""

    repo_id: str = Field(..., description="Repo UUID to add")
    is_primary: bool = Field(False, description="Whether this is the primary repo")
    custom_setup_script: str | None = Field(
        None, description="Per-board setup script override"
    )
    custom_cleanup_script: str | None = Field(
        None, description="Per-board cleanup script override"
    )


class BoardRepoUpdate(BaseModel):
    """Schema for updating board-repo association."""

    is_primary: bool | None = Field(None, description="Set as primary repo")
    custom_setup_script: str | None = Field(
        None, description="Per-board setup script override"
    )
    custom_cleanup_script: str | None = Field(
        None, description="Per-board cleanup script override"
    )


class BoardRepoResponse(BoardRepoBase):
    """Schema for board-repo API responses."""

    id: str = Field(..., description="BoardRepo UUID")
    repo: RepoResponse = Field(..., description="Repo details")
    created_at: datetime = Field(..., description="When association was created")

    class Config:
        from_attributes = True


class BoardRepoListResponse(BaseModel):
    """Schema for board repos list API response."""

    board_id: str = Field(..., description="Board UUID")
    repos: list[BoardRepoResponse] = Field(..., description="List of repos for board")
    total: int = Field(..., description="Total number of repos")
