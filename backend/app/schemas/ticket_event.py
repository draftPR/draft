"""Pydantic schemas for TicketEvent entity."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, computed_field

from app.state_machine import ActorType, EventType, TicketState


class TicketEventResponse(BaseModel):
    """Schema for ticket event response."""

    id: str
    ticket_id: str
    event_type: EventType
    from_state: TicketState | None
    to_state: TicketState | None
    actor_type: ActorType
    actor_id: str | None
    reason: str | None
    payload: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def event_type_display(self) -> str:
        """Human-readable event type."""
        display_map = {
            EventType.CREATED: "Created",
            EventType.TRANSITIONED: "Transitioned",
            EventType.UPDATED: "Updated",
            EventType.COMMENT: "Comment",
        }
        return display_map.get(self.event_type, self.event_type.value.title())

    @computed_field
    @property
    def actor_type_display(self) -> str:
        """Human-readable actor type."""
        display_map = {
            ActorType.HUMAN: "Human",
            ActorType.PLANNER: "AI Planner",
            ActorType.EXECUTOR: "AI Executor",
            ActorType.SYSTEM: "System",
        }
        return display_map.get(self.actor_type, self.actor_type.value.title())

    @computed_field
    @property
    def from_state_display(self) -> str | None:
        """Human-readable from state."""
        if self.from_state is None:
            return None
        return self.from_state.value.replace("_", " ").title()

    @computed_field
    @property
    def to_state_display(self) -> str | None:
        """Human-readable to state."""
        if self.to_state is None:
            return None
        return self.to_state.value.replace("_", " ").title()


class TicketEventListResponse(BaseModel):
    """Schema for list of ticket events response."""

    events: list[TicketEventResponse]
    total: int
