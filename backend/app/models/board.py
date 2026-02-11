"""Board model - the primary permission and scoping boundary."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board_repo import BoardRepo
    from app.models.goal import Goal
    from app.models.job import Job
    from app.models.ticket import Ticket
    from app.models.workspace import Workspace


class Board(Base):
    """Board represents a project/repository boundary.
    
    Key properties:
    - Single repo per board (repo_root is authoritative)
    - All goals, tickets, jobs, workspaces belong to a board
    - board_id is the permission boundary for all operations
    
    This prevents cross-tenant/cross-project data access.
    """

    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # The authoritative repo root for this board
    # All file operations use this path - NOT client-provided paths
    repo_root: Mapped[str] = mapped_column(String(1024), nullable=False)
    
    # Optional: default branch for this repo
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Board-level configuration overrides (JSON)
    # Overrides settings from smartkanban.yaml
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    goals: Mapped[list["Goal"]] = relationship(
        "Goal", back_populates="board", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="board", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="board", cascade="all, delete-orphan"
    )
    workspaces: Mapped[list["Workspace"]] = relationship(
        "Workspace", back_populates="board", cascade="all, delete-orphan"
    )
    board_repos: Mapped[list["BoardRepo"]] = relationship(
        "BoardRepo", back_populates="board", cascade="all, delete-orphan"
    )


