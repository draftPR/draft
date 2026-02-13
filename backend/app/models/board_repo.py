"""BoardRepo junction model - Board <-> Repo many-to-many relationship."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.repo import Repo


class BoardRepo(Base):
    """Junction table linking Boards to Repos (many-to-many).

    Allows a board to have multiple repositories and a repo to be
    shared across multiple boards.

    Key properties:
    - board_id + repo_id must be unique (one entry per board-repo pair)
    - is_primary marks the primary repo for a board (used as default for operations)
    - custom_setup_script allows per-board repo configuration overrides
    """

    __tablename__ = "board_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Foreign keys
    board_id: Mapped[str] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repo_id: Mapped[str] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Primary repo flag - each board should have exactly one primary repo
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Per-board repo overrides (optional)
    custom_setup_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_cleanup_script: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    board: Mapped["Board"] = relationship("Board", back_populates="board_repos")
    repo: Mapped["Repo"] = relationship("Repo", back_populates="board_repos")

    # Constraints
    __table_args__ = (
        UniqueConstraint("board_id", "repo_id", name="uq_board_repo"),
    )

    def __repr__(self) -> str:
        return f"<BoardRepo(board_id={self.board_id}, repo_id={self.repo_id}, is_primary={self.is_primary})>"
