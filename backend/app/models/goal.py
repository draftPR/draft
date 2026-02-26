"""Goal model for Alma Kanban."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.agent_conversation_history import AgentConversationHistory
    from app.models.board import Board
    from app.models.cost_budget import CostBudget
    from app.models.merge_checklist import MergeChecklist
    from app.models.ticket import Ticket


class Goal(Base):
    """Goal model representing a high-level objective.

    IMPORTANT: Goals are scoped by board_id for permission enforcement.
    """

    __tablename__ = "goals"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    # Autonomy fields
    autonomy_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    auto_approve_tickets: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    auto_approve_revisions: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    auto_merge: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    auto_approve_followups: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    max_auto_approvals: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True
    )
    auto_approval_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Relationships
    board: Mapped["Board | None"] = relationship("Board", back_populates="goals")
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        back_populates="goal",
        cascade="all, delete-orphan",
    )
    budget: Mapped["CostBudget | None"] = relationship(
        "CostBudget",
        back_populates="goal",
        uselist=False,
        cascade="all, delete-orphan",
    )
    merge_checklist: Mapped["MergeChecklist | None"] = relationship(
        "MergeChecklist",
        back_populates="goal",
        uselist=False,
        cascade="all, delete-orphan",
    )
    agent_conversation_history: Mapped[list["AgentConversationHistory"]] = relationship(
        "AgentConversationHistory",
        back_populates="goal",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Goal(id={self.id}, title={self.title})>"
