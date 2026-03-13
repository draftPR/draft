"""Pydantic response models for the Draft SDK."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# -- Board -------------------------------------------------------------------

class Board(BaseModel):
    id: str
    name: str | None = None
    repo_root: str | None = None
    description: str | None = None
    base_branch: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# -- Goal --------------------------------------------------------------------

class Goal(BaseModel):
    id: str
    board_id: str | None = None
    title: str
    description: str | None = None
    status: str | None = None
    autonomy_enabled: bool = False
    auto_approve_tickets: bool = False
    auto_approve_revisions: bool = False
    auto_merge: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


# -- Ticket ------------------------------------------------------------------

class Ticket(BaseModel):
    id: str
    goal_id: str | None = None
    board_id: str | None = None
    title: str
    description: str | None = None
    state: str
    priority: int | None = None
    blocked_by_ticket_id: str | None = None
    sort_order: int | None = None
    pr_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BulkAcceptResult(BaseModel):
    accepted: int = 0
    queued: int = 0
    skipped: int = 0


# -- Job ---------------------------------------------------------------------

class Job(BaseModel):
    id: str
    ticket_id: str | None = None
    board_id: str | None = None
    kind: str | None = None
    status: str
    variant: str | None = None
    exit_code: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


# -- Revision ----------------------------------------------------------------

class Revision(BaseModel):
    id: str
    ticket_id: str | None = None
    job_id: str | None = None
    number: int | None = None
    status: str | None = None
    created_at: datetime | None = None


class ReviewComment(BaseModel):
    id: str
    revision_id: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    content: str | None = None
    is_resolved: bool = False
    created_at: datetime | None = None


class ReviewSummary(BaseModel):
    id: str | None = None
    revision_id: str | None = None
    decision: str | None = None
    body: str | None = None
    created_at: datetime | None = None


class RevisionDiff(BaseModel):
    stat: str | None = None
    patch: str | None = None


# -- Progress ----------------------------------------------------------------

class GoalProgress(BaseModel):
    goal_id: str
    total_tickets: int = 0
    by_state: dict[str, int] = Field(default_factory=dict)
    completion_pct: float = 0.0
    is_blocked: bool = False


# -- GoalResult (high-level) -------------------------------------------------

class GoalResult(BaseModel):
    goal: Goal
    status: str  # completed, partial, no_tickets, executing, blocked
    tickets: list[Ticket] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def blocked_tickets(self) -> list[Ticket]:
        return [t for t in self.tickets if t.state == "blocked"]

    @property
    def done_tickets(self) -> list[Ticket]:
        return [t for t in self.tickets if t.state == "done"]
