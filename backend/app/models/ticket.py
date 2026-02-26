"""Ticket model for Alma Kanban."""

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.state_machine import TicketState

if TYPE_CHECKING:
    from app.models.agent_session import AgentSession
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

    BLOCKING/DEPENDENCIES:
    - blocked_by_ticket_id: If set, this ticket is blocked by another ticket
    - A ticket cannot be queued for execution until its blocker is DONE
    - When generating tickets, the agent can specify dependencies
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
    # Blocking/dependency: If set, this ticket cannot be executed until the blocker is DONE
    blocked_by_ticket_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    # GitHub Pull Request fields
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pr_state: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # 'OPEN', 'CLOSED', 'MERGED'
    pr_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pr_merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pr_head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
    agent_sessions: Mapped[list["AgentSession"]] = relationship(
        "AgentSession",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="AgentSession.created_at.desc()",
    )

    # Blocking relationship (self-referential)
    blocked_by: Mapped["Ticket | None"] = relationship(
        "Ticket",
        foreign_keys=[blocked_by_ticket_id],
        remote_side="Ticket.id",
        uselist=False,
        back_populates="blocking",
    )
    # Tickets that this ticket is blocking
    blocking: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        foreign_keys="Ticket.blocked_by_ticket_id",
        back_populates="blocked_by",
    )

    @property
    def state_enum(self) -> TicketState:
        """Get the state as a TicketState enum."""
        return TicketState(self.state)

    @property
    def is_blocked_by_dependency(self) -> bool:
        """Check if this ticket is blocked by an incomplete dependency.

        Returns True if:
        - blocked_by_ticket_id is set, AND
        - The blocking ticket's state is NOT 'done'

        Note: This requires the blocked_by relationship to be loaded.
        Use selectinload(Ticket.blocked_by) when querying.
        """
        if not self.blocked_by_ticket_id:
            return False
        if self.blocked_by is None:
            # Relationship not loaded - assume blocked for safety
            return True
        return self.blocked_by.state != TicketState.DONE.value

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
