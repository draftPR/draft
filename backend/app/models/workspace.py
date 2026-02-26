"""Workspace model for git worktree isolation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.ticket import Ticket


class Workspace(Base):
    """Workspace model representing an isolated git worktree for a ticket.

    IMPORTANT: Workspaces are scoped by board_id for permission enforcement.
    """

    __tablename__ = "workspaces"

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
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    worktree_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    branch_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    cleaned_up_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Relationships
    board: Mapped["Board | None"] = relationship("Board", back_populates="workspaces")
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="workspace")

    @property
    def is_active(self) -> bool:
        """Check if the workspace is still active (not cleaned up)."""
        return self.cleaned_up_at is None

    def __repr__(self) -> str:
        return f"<Workspace(id={self.id}, ticket_id={self.ticket_id}, branch={self.branch_name})>"

