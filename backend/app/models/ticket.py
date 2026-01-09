"""Ticket model for Smart Kanban."""

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.state_machine import TicketState

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.evidence import Evidence
    from app.models.goal import Goal
    from app.models.job import Job
    from app.models.revision import Revision
    from app.models.ticket_event import TicketEvent
    from app.models.workspace import Workspace


class Ticket(Base):
    """Ticket model representing a unit of work.
    
    IMPORTANT: Tickets are scoped by board_id for permission enforcement.
    The board_id should match the goal's board_id.
    """

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    board_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=True,  # Nullable for migration compatibility
        index=True,
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
    verification_commands_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="JSON array of verification commands"
    )
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
    board: Mapped["Board | None"] = relationship("Board", back_populates="tickets")
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
    revisions: Mapped[list["Revision"]] = relationship(
        "Revision",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="Revision.number.desc()",
    )

    @property
    def state_enum(self) -> TicketState:
        """Get the state as a TicketState enum."""
        return TicketState(self.state)

    @property
    def verification_commands(self) -> list[str]:
        """Get verification commands as a list."""
        if not self.verification_commands_json:
            return []
        try:
            return json.loads(self.verification_commands_json)
        except (json.JSONDecodeError, TypeError):
            return []

    @verification_commands.setter
    def verification_commands(self, commands: list[str]) -> None:
        """Set verification commands from a list with validation."""
        if not commands:
            self.verification_commands_json = None
            return
        
        # Validation constants
        MAX_COMMANDS = 5
        MAX_CMD_LENGTH = 500
        
        # Validate and sanitize
        validated = []
        for cmd in commands[:MAX_COMMANDS]:
            if not isinstance(cmd, str):
                continue
            # Truncate if too long
            cmd = cmd[:MAX_CMD_LENGTH].strip()
            # Skip empty commands
            if not cmd:
                continue
            # Remove null bytes and control chars
            cmd = "".join(c for c in cmd if ord(c) >= 32 or c in "\t\n\r")
            validated.append(cmd)
        
        if validated:
            self.verification_commands_json = json.dumps(validated)
        else:
            self.verification_commands_json = None

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, title={self.title}, state={self.state})>"
