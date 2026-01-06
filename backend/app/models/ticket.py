"""Ticket model for Smart Kanban."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.state_machine import TicketState

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.goal import Goal
    from app.models.job import Job
    from app.models.ticket_event import TicketEvent
    from app.models.workspace import Workspace


class Ticket(Base):
    """Ticket model representing a unit of work."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    goal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        String(50),
        default=TicketState.PROPOSED.value,
        nullable=False,
        index=True,
    )
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="tickets")
    events: Mapped[list["TicketEvent"]] = relationship(
        "TicketEvent",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketEvent.created_at",
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Job.created_at.desc()",
    )
    workspace: Mapped["Workspace | None"] = relationship(
        "Workspace",
        back_populates="ticket",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Evidence.created_at.desc()",
    )

    @property
    def state_enum(self) -> TicketState:
        """Get the state as a TicketState enum."""
        return TicketState(self.state)

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, title={self.title}, state={self.state})>"
