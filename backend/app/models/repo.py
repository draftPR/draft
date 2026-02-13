"""Repo model - global repository registry."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board_repo import BoardRepo


class Repo(Base):
    """Global repository registry.

    Each Repo represents a git repository on the filesystem.
    Repos can be associated with multiple boards via BoardRepo junction table.

    Key properties:
    - path is unique - only one Repo per filesystem path
    - display_name is user-friendly name for UI
    - Optional scripts for setup/cleanup/dev server
    - Git metadata (default_branch, remote_url) cached for performance
    """

    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Filesystem path to git repository (unique)
    path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)

    # Repository name (derived from path, e.g., "my-project")
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # User-friendly display name (editable)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optional per-repo scripts
    setup_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleanup_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    dev_server_script: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Git metadata (cached)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    board_repos: Mapped[list["BoardRepo"]] = relationship(
        "BoardRepo", back_populates="repo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Repo(id={self.id}, name={self.name}, path={self.path})>"
