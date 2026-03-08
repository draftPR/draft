"""TicketEvent model for Draft - append-only event log."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class TicketEvent(Base):
    """
    TicketEvent model for recording all ticket state changes and actions.

    This is an append-only log - events should never be updated or deleted.
    """

    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    from_state: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    to_state: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    payload_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="events")

    def get_payload(self) -> dict[str, Any] | None:
        """Parse and return the payload as a dictionary."""
        if self.payload_json is None:
            return None
        import json

        return json.loads(self.payload_json)

    def __repr__(self) -> str:
        return f"<TicketEvent(id={self.id}, type={self.event_type}, ticket_id={self.ticket_id})>"
