"""Pydantic schemas for merge operations."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MergeStrategy(StrEnum):
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
        description="Warning if merge succeeded without pulling latest (local-only merge)",
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


class ConflictStatusResponse(BaseModel):
    """Response for conflict status query."""

    has_conflict: bool
    operation: str | None = Field(
        description="Type of conflict operation: rebase, merge, cherry_pick, revert"
    )
    conflicted_files: list[str] = Field(default_factory=list)
    can_continue: bool = False
    can_abort: bool = False
    divergence: dict | None = Field(
        default=None,
        description="Branch divergence info (ahead/behind counts)",
    )


class RebaseResponse(BaseModel):
    """Response from a rebase operation."""

    success: bool
    message: str
    has_conflicts: bool = False
    conflicted_files: list[str] = Field(default_factory=list)


class AbortResponse(BaseModel):
    """Response from an abort operation."""

    success: bool
    message: str


class PushResponse(BaseModel):
    """Response from a push operation."""

    success: bool
    message: str


class PushStatusResponse(BaseModel):
    """Response for push status query."""

    ahead: int = 0
    behind: int = 0
    remote_exists: bool = False
    needs_push: bool = False


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
        description="Worktrees skipped due to ticket state (executing/verifying/needs_human)",
    )
    evidence_files_deleted: int
    evidence_files_failed: int
    bytes_freed: int
    details: list[str]
