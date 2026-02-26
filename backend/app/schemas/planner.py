"""Pydantic schemas for AI Planner feature."""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# Validation Constants
# =============================================================================

MAX_VERIFICATION_COMMANDS = 5
MAX_COMMAND_LENGTH = 500
FORBIDDEN_PATTERNS = [
    rb"\x00",  # Null bytes
    rb"[\x00-\x08\x0b\x0c\x0e-\x1f]",  # Control characters (except tab, newline, carriage return)
]


def validate_verification_command(cmd: str) -> str:
    """Validate a single verification command."""
    if len(cmd) > MAX_COMMAND_LENGTH:
        raise ValueError(f"Command exceeds {MAX_COMMAND_LENGTH} characters")

    cmd_bytes = cmd.encode("utf-8", errors="replace")
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cmd_bytes):
            raise ValueError("Command contains forbidden control characters")

    return cmd.strip()


# =============================================================================
# Priority Bucket System
# =============================================================================


class PriorityBucket(StrEnum):
    """Priority buckets for deterministic prioritization.

    Using buckets instead of raw 0-100 values prevents LLM "priority inflation"
    where everything ends up in the 80-90 range.

    Numeric values are derived from buckets:
    - P0 = 90 (Critical: security issues, blocking bugs)
    - P1 = 70 (High: important features, performance)
    - P2 = 50 (Medium: improvements, nice-to-haves)
    - P3 = 30 (Low: cleanup, documentation)
    """

    P0 = "P0"  # Critical -> 90
    P1 = "P1"  # High -> 70
    P2 = "P2"  # Medium -> 50
    P3 = "P3"  # Low -> 30


# Bucket to numeric priority mapping
PRIORITY_BUCKET_VALUES = {
    PriorityBucket.P0: 90,
    PriorityBucket.P1: 70,
    PriorityBucket.P2: 50,
    PriorityBucket.P3: 30,
}


def bucket_to_priority(bucket: PriorityBucket | str) -> int:
    """Convert a priority bucket to a numeric priority value."""
    if isinstance(bucket, str):
        bucket = PriorityBucket(bucket)
    return PRIORITY_BUCKET_VALUES[bucket]


def priority_to_bucket(priority: int) -> PriorityBucket:
    """Convert a numeric priority to the nearest bucket."""
    if priority >= 80:
        return PriorityBucket.P0
    elif priority >= 60:
        return PriorityBucket.P1
    elif priority >= 40:
        return PriorityBucket.P2
    else:
        return PriorityBucket.P3


# =============================================================================
# Ticket Generation Schemas
# =============================================================================


class ProposedTicketSchema(BaseModel):
    """Schema for a single proposed ticket from the LLM planner."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    verification: list[str] = Field(
        default_factory=list,
        description="Commands to verify the ticket implementation",
        max_length=MAX_VERIFICATION_COMMANDS,
    )
    notes: str | None = Field(None, description="Optional context or notes")
    blocked_by: str | None = Field(
        None,
        description="Title of another ticket in this batch that blocks this one. "
        "The ticket cannot be executed until the blocker is DONE.",
    )

    @field_validator("verification", mode="before")
    @classmethod
    def validate_verification_commands(cls, v: list[str] | None) -> list[str]:
        """Validate and sanitize verification commands."""
        if not v:
            return []

        if not isinstance(v, list):
            raise ValueError(f"verification must be a list, got {type(v).__name__}")

        if len(v) > MAX_VERIFICATION_COMMANDS:
            v = v[:MAX_VERIFICATION_COMMANDS]

        validated = []
        for cmd in v:
            if not isinstance(cmd, str):
                continue
            try:
                validated.append(validate_verification_command(cmd))
            except ValueError:
                continue

        return validated


class GeneratedTicket(BaseModel):
    """Schema for a generated ticket with priority bucket."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority_bucket: PriorityBucket = Field(
        ..., description="Priority bucket (P0-P3)"
    )
    priority: int = Field(..., ge=0, le=100, description="Derived numeric priority")
    priority_rationale: str = Field(
        ..., description="Explanation for the assigned priority"
    )
    verification: list[str] = Field(default_factory=list)
    notes: str | None = None
    blocked_by: str | None = Field(
        None,
        description="Title of another ticket that blocks this one",
    )

    @field_validator("verification", mode="before")
    @classmethod
    def validate_verification_commands(cls, v: list[str] | None) -> list[str]:
        """Validate and sanitize verification commands."""
        if not v:
            return []
        if not isinstance(v, list):
            return []
        validated = []
        for cmd in v[:MAX_VERIFICATION_COMMANDS]:
            if isinstance(cmd, str):
                try:
                    validated.append(validate_verification_command(cmd))
                except ValueError:
                    continue
        return validated


class GenerateTicketsRequest(BaseModel):
    """Request schema for generating tickets from a goal.

    SECURITY NOTE: The repository path is ALWAYS inferred from server config
    (smartkanban.yaml repo_root). This prevents directory traversal attacks.
    """

    model_config = ConfigDict(extra="ignore")

    include_readme: bool = Field(
        default=False,
        description="Whether to include README excerpt in context",
    )


class CreatedTicketSchema(BaseModel):
    """Schema for a created ticket with its ID."""

    id: str = Field(..., description="ID of the created ticket")
    title: str
    description: str
    priority_bucket: PriorityBucket | None = Field(
        None, description="Priority bucket if generated with buckets"
    )
    priority: int | None = Field(None, description="Numeric priority (0-100)")
    priority_rationale: str | None = Field(
        None, description="Explanation for the assigned priority"
    )
    verification: list[str] = Field(default_factory=list)
    notes: str | None = None
    blocked_by_ticket_id: str | None = Field(
        None, description="ID of the ticket that blocks this one"
    )
    blocked_by_title: str | None = Field(
        None, description="Title of the ticket that blocks this one (for display)"
    )


class GenerateTicketsResponse(BaseModel):
    """Response schema containing generated proposed tickets."""

    tickets: list[CreatedTicketSchema] = Field(
        default_factory=list,
        description="List of proposed tickets created by the planner",
    )
    goal_id: str = Field(..., description="ID of the goal these tickets belong to")


class LLMTicketsResponse(BaseModel):
    """Schema for parsing the raw LLM JSON response."""

    tickets: list[ProposedTicketSchema]


# =============================================================================
# Codebase Analysis Schemas
# =============================================================================


class ExcludedMatch(BaseModel):
    """A pattern that caused files to be excluded."""

    pattern: str = Field(..., description="The exclusion pattern that matched")
    count: int = Field(..., description="Number of files excluded by this pattern")


class FiletypeCount(BaseModel):
    """Count of files by extension/type."""

    extension: str = Field(..., description="File extension (e.g., '.py', '.ts')")
    count: int = Field(..., description="Number of files with this extension")


class ContextStats(BaseModel):
    """Statistics from context gathering for observability and debugging."""

    files_scanned: int = Field(0, description="Number of files scanned")
    todos_collected: int = Field(0, description="Number of TODO/FIXME comments found")
    context_truncated: bool = Field(
        False, description="Whether context was truncated due to caps"
    )
    skipped_excluded: int = Field(0, description="Files skipped due to exclusion rules")
    skipped_symlinks: int = Field(0, description="Symlinks skipped for security")
    bytes_read: int = Field(0, description="Total bytes read from files")
    # New observability fields
    excluded_matches: list[ExcludedMatch] = Field(
        default_factory=list,
        description="Top exclusion patterns hit (capped to 10)",
    )
    filetype_histogram: list[FiletypeCount] = Field(
        default_factory=list,
        description="Top file extensions scanned (capped to 10)",
    )


class SimilarTicketWarning(BaseModel):
    """Warning about a ticket that was similar to an existing one."""

    proposed_title: str = Field(..., description="Title of the proposed ticket")
    similar_to_id: str = Field(..., description="ID of the similar existing ticket")
    similar_to_title: str = Field(..., description="Title of the similar existing ticket")
    similarity_score: float = Field(..., description="Similarity score (0-1)")


class AnalyzeCodebaseRequest(BaseModel):
    """Request schema for analyzing a codebase to generate tickets."""

    goal_id: str | None = Field(
        None,
        description="If provided, attach generated tickets to this goal",
    )
    focus_areas: list[str] | None = Field(
        None,
        description="Optional focus hints: ['security', 'performance', 'tests', 'docs']",
    )
    include_readme: bool = Field(
        default=False,
        description="Whether to include README excerpt in analysis",
    )


class AnalyzeCodebaseResponse(BaseModel):
    """Response schema for codebase analysis."""

    tickets: list[CreatedTicketSchema] = Field(
        default_factory=list,
        description="Generated tickets from codebase analysis",
    )
    goal_id: str | None = Field(
        None,
        description="Goal ID if tickets were attached to a goal",
    )
    analysis_summary: str = Field(
        ...,
        description="High-level summary of codebase findings",
    )
    cache_hit: bool = Field(
        default=False,
        description="Whether this result was served from cache",
    )
    context_stats: ContextStats | None = Field(
        None,
        description="Statistics from context gathering (quality indicators)",
    )
    similar_warnings: list[SimilarTicketWarning] = Field(
        default_factory=list,
        description="Tickets skipped due to similarity (not exact match)",
    )
    repo_head_sha: str | None = Field(
        None,
        description="Git HEAD SHA of main repo at time of analysis (full 40-char SHA)",
    )
    workspace_head_sha: str | None = Field(
        None,
        description="Git HEAD SHA of workspace if different from repo root (for worktrees)",
    )


# =============================================================================
# Reflection Schemas
# =============================================================================


class SuggestedPriorityChange(BaseModel):
    """A suggested change to a ticket's priority."""

    ticket_id: str
    ticket_title: str
    current_bucket: PriorityBucket
    current_priority: int
    suggested_bucket: PriorityBucket
    suggested_priority: int
    reason: str


class ReflectionResult(BaseModel):
    """Result of reflecting on proposed tickets."""

    overall_quality: Literal["good", "needs_work", "insufficient"] = Field(
        ..., description="Overall assessment of ticket quality"
    )
    quality_notes: str = Field(
        ..., description="Detailed notes on ticket quality"
    )
    coverage_gaps: list[str] = Field(
        default_factory=list,
        description="Areas not covered by current tickets",
    )
    suggested_changes: list[SuggestedPriorityChange] = Field(
        default_factory=list,
        description="Suggested priority adjustments",
    )


# =============================================================================
# Bulk Priority Update Schemas
# =============================================================================


class PriorityUpdate(BaseModel):
    """A single priority update request."""

    ticket_id: str
    priority_bucket: PriorityBucket


class BulkPriorityUpdateRequest(BaseModel):
    """Request to update priorities for multiple tickets.

    AUTHORIZATION: board_id is REQUIRED. All tickets must belong to this board.

    SAFETY: P0 assignments require explicit allow_p0=true flag and are
    limited to MAX_P0_PER_REQUEST (default 3) per request.
    """

    board_id: str = Field(
        ...,
        description="Board ID - all tickets must belong to this board (authorization boundary)",
    )
    goal_id: str = Field(
        ...,
        description="Goal ID - all tickets must belong to this goal",
    )
    updates: list[PriorityUpdate] = Field(
        ..., min_length=1, description="List of priority updates to apply"
    )
    allow_p0: bool = Field(
        default=False,
        description="Must be true to assign P0 priority. Safety guard against accidental critical escalation.",
    )


# Server-side P0 safety limits
MAX_P0_PER_REQUEST = 3


class BulkPriorityUpdateResult(BaseModel):
    """Result for a single ticket in bulk priority update."""

    ticket_id: str
    success: bool
    new_priority: int | None = None
    new_bucket: PriorityBucket | None = None
    error: str | None = None


class BulkPriorityUpdateResponse(BaseModel):
    """Response for bulk priority update operation."""

    updated: list[BulkPriorityUpdateResult] = Field(default_factory=list)
    updated_count: int
    failed_count: int


# =============================================================================
# Planner Tick Schemas
# =============================================================================


class PlannerActionType(str):
    """Types of actions the planner can take."""

    ENQUEUED_EXECUTE = "enqueued_execute"
    PROPOSED_FOLLOWUP = "proposed_followup"
    GENERATED_REFLECTION = "generated_reflection"
    SKIPPED = "skipped"


class PlannerAction(BaseModel):
    """A single action taken by the planner during a tick."""

    action_type: str = Field(..., description="Type of action taken")
    ticket_id: str = Field(..., description="ID of the ticket affected")
    ticket_title: str | None = Field(None, description="Title of the ticket for display")
    details: dict | None = Field(None, description="Additional details about the action")


class PlannerTickResponse(BaseModel):
    """Response from a planner tick operation."""

    actions: list[PlannerAction] = Field(
        default_factory=list,
        description="List of actions taken during this tick",
    )
    summary: str = Field(
        ...,
        description="Human-readable summary of what happened",
    )


class PlannerTickRequest(BaseModel):
    """Request for a planner tick operation (currently empty, for future expansion)."""

    pass


class PlannerStartRequest(BaseModel):
    """Request for starting the autopilot loop."""

    poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Seconds to wait between checking queue status",
    )
    max_duration_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Maximum time to run the autopilot loop (1 hour default, max 24 hours)",
    )


class PlannerStartResponse(BaseModel):
    """Response from starting the autopilot."""

    status: str = Field(..., description="'running', 'completed', or 'error'")
    message: str = Field(..., description="Human-readable status message")
    tickets_queued: int = Field(default=0, description="Number of tickets initially queued")
    tickets_completed: int = Field(default=0, description="Number of tickets completed")
    tickets_failed: int = Field(default=0, description="Number of tickets that failed/blocked")
    total_actions: list[PlannerAction] = Field(
        default_factory=list,
        description="All actions taken during the autopilot run",
    )
