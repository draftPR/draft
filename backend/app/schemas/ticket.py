"""Pydantic schemas for Ticket entity."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.state_machine import ActorType, TicketState


class TicketCreate(BaseModel):
    """Schema for creating a new ticket."""

    goal_id: str = Field(..., description="UUID of the parent goal")
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: int | None = Field(None, ge=0, le=100)
    actor_type: ActorType = Field(
        default=ActorType.HUMAN,
        description="Type of actor creating the ticket",
    )
    actor_id: str | None = Field(
        None, description="ID of the actor creating the ticket"
    )


class TicketResponse(BaseModel):
    """Schema for ticket response."""

    id: str
    goal_id: str
    title: str
    description: str | None
    state: TicketState
    priority: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketDetailResponse(TicketResponse):
    """Schema for detailed ticket response with additional context."""

    goal_title: str | None = None
    goal_description: str | None = None
    priority_label: str | None = None
    state_display: str

    @staticmethod
    def get_priority_label(priority: int | None) -> str | None:
        """Convert numeric priority to human-readable label."""
        if priority is None:
            return None
        if priority >= 80:
            return "High"
        elif priority >= 50:
            return "Medium"
        elif priority >= 20:
            return "Low"
        else:
            return "Very Low"

    @staticmethod
    def get_state_display(state: TicketState) -> str:
        """Convert state enum to human-readable display text."""
        display_map = {
            TicketState.PROPOSED: "Proposed",
            TicketState.PLANNED: "Planned",
            TicketState.EXECUTING: "Executing",
            TicketState.VERIFYING: "Verifying",
            TicketState.NEEDS_HUMAN: "Needs Human",
            TicketState.BLOCKED: "Blocked",
            TicketState.DONE: "Done",
            TicketState.ABANDONED: "Abandoned",
        }
        return display_map.get(state, state.value.title())


class TicketTransition(BaseModel):
    """Schema for requesting a ticket state transition."""

    to_state: TicketState = Field(..., description="Target state for the transition")
    actor_type: ActorType = Field(
        ..., description="Type of actor performing the transition"
    )
    actor_id: str | None = Field(
        None, description="ID of the actor performing the transition"
    )
    reason: str | None = Field(None, description="Reason for the state transition")


class TicketWithGoal(TicketResponse):
    """Schema for ticket response including goal information."""

    goal_title: str | None = None


class TicketsByState(BaseModel):
    """Schema for tickets grouped by state."""

    state: TicketState
    tickets: list[TicketResponse]


class BoardResponse(BaseModel):
    """Schema for the board view - tickets grouped by state."""

    columns: list[TicketsByState]
    total_tickets: int


class BulkAcceptRequest(BaseModel):
    """Schema for bulk accepting proposed tickets."""

    ticket_ids: list[str] = Field(..., min_length=1, description="List of ticket IDs to accept")
    goal_id: str | None = Field(
        None,
        description="If provided, validates all tickets belong to this goal",
    )
    actor_type: ActorType = Field(default=ActorType.HUMAN, description="Actor performing the accept")
    actor_id: str | None = Field(None, description="ID of the actor")
    reason: str | None = Field(
        default="Accepted from AI-generated proposal",
        description="Reason for acceptance",
    )
    queue_first: bool = Field(
        default=False,
        description="If true, queue the first accepted ticket for execution",
    )


class BulkAcceptResult(BaseModel):
    """Result for a single ticket in bulk accept."""

    ticket_id: str
    success: bool
    error: str | None = None


class BulkAcceptResponse(BaseModel):
    """Response for bulk accept operation."""

    accepted_ids: list[str] = Field(default_factory=list)
    rejected: list[BulkAcceptResult] = Field(default_factory=list)
    accepted_count: int
    failed_count: int
    queued_job_id: str | None = Field(
        None,
        description="Job ID if queue_first was true and first ticket was queued",
    )
    queued_ticket_id: str | None = Field(
        None,
        description="Ticket ID that was queued (first in request order)",
    )
