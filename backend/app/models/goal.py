"""Goal model for Smart Kanban."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.cost_budget import CostBudget
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

    def __repr__(self) -> str:
        return f"<Goal(id={self.id}, title={self.title})>"
