"""Pydantic schemas for merge operations."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MergeStrategy(str, Enum):
    """Supported merge strategies."""

    MERGE = "merge"
    REBASE = "rebase"


class MergeRequest(BaseModel):
    """Request body for merging a ticket's changes."""

    strategy: MergeStrategy = MergeStrategy.MERGE
    delete_worktree: bool = Field(
        default=True,
        description="Delete the worktree after successful merge",
    )
    cleanup_artifacts: bool = Field(
        default=True,
        description="Clean up evidence files after successful merge",
    )


class MergeResponse(BaseModel):
    """Response from a merge operation."""

    success: bool
    message: str
    exit_code: int
    evidence_id: str | None = None
    pull_warning: str | None = Field(
        default=None,
        description="Warning if merge succeeded without pulling latest (local-only merge)"
    )


class MergeStatusResponse(BaseModel):
    """Response for merge status query."""

    ticket_id: str
    can_merge: bool = Field(
        description="Whether the ticket can be merged (done state, approved revision, active worktree)"
    )
    is_merged: bool = Field(
        description="Whether the ticket has been successfully merged"
    )
    has_approved_revision: bool
    workspace: dict | None = Field(
        description="Workspace info with worktree_path and branch_name"
    )
    last_merge_attempt: dict | None = Field(
        description="Info about the last merge attempt event"
    )


class CleanupRequest(BaseModel):
    """Request body for maintenance cleanup."""

    dry_run: bool = Field(
        default=True,
        description="If true, only report what would be deleted without actually deleting",
    )
    delete_worktrees: bool = Field(
        default=True,
        description="Delete stale and orphaned worktrees",
    )
    delete_evidence: bool = Field(
        default=True,
        description="Delete old evidence files",
    )


class CleanupResponse(BaseModel):
    """Response from a cleanup operation."""

    dry_run: bool
    worktrees_deleted: int
    worktrees_failed: int
    worktrees_skipped: int = Field(
        default=0,
        description="Worktrees skipped due to ticket state (executing/verifying/needs_human)"
    )
    evidence_files_deleted: int
    evidence_files_failed: int
    bytes_freed: int
    details: list[str]

