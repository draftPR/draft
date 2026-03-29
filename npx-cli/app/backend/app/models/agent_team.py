"""Agent team models for multi-agent collaboration.

Enables coral-style multi-agent teams where specialized agents (team lead,
developer, reviewer, QA, etc.) collaborate on tickets via tmux sessions
and a message board.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentTeam(Base):
    """A configured team of agents for a board.

    Each board can have one active agent team. The team defines
    which agent roles participate in ticket execution.
    """

    __tablename__ = "agent_teams"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    board_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Default Team"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    board: Mapped["Board"] = relationship("Board", back_populates="agent_team")  # noqa: F821
    members: Mapped[list["AgentTeamMember"]] = relationship(
        "AgentTeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="AgentTeamMember.sort_order",
    )


class AgentTeamMember(Base):
    """A single agent role within a team.

    Defines the role, executor type, and behavior prompt for one
    agent in the team. The team lead (orchestrator) is required.
    """

    __tablename__ = "agent_team_members"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    team_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "team_lead", "developer", "qa"
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # e.g., "Team Lead", "Backend Dev"
    executor_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="claude"
    )  # "claude", "cursor-agent", "codex", etc.
    behavior_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Role-specific system prompt
    receive_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="mentions"
    )  # "all" (orchestrator) or "mentions" (workers)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    team: Mapped["AgentTeam"] = relationship("AgentTeam", back_populates="members")
    sessions: Mapped[list["TeamAgentSession"]] = relationship(
        "TeamAgentSession",
        back_populates="team_member",
        cascade="all, delete-orphan",
    )


class TeamAgentSession(Base):
    """A running agent instance for a specific ticket execution.

    Created when a team is launched for a ticket. Tracks the tmux session,
    log file, and current status of each agent.
    """

    __tablename__ = "team_agent_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_member_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_team_members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tmux_session_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    session_uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4())
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, running, waiting, done, failed
    log_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_pulse_status: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_pulse_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_pulse_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    team_member: Mapped["AgentTeamMember"] = relationship(
        "AgentTeamMember", back_populates="sessions"
    )


class BoardMessage(Base):
    """A message on the team message board for inter-agent communication.

    Scoped to a board + ticket execution. Agents post and read messages
    via the board CLI. Uses cursor-based reads so each agent only sees
    new messages since their last read.
    """

    __tablename__ = "board_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BoardMessageCursor(Base):
    """Tracks the last-read message ID per agent session per ticket.

    Enables cursor-based reads: each agent only receives messages
    posted after their last read position.
    """

    __tablename__ = "board_message_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ticket_id: Mapped[str] = mapped_column(String(36), nullable=False)
    last_read_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
