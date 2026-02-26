"""Planner lock model for ensuring single-tick execution."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlannerLock(Base):
    """Single-row lock table to prevent concurrent planner ticks.

    This ensures that only one planner tick can run at a time,
    preventing race conditions where two ticks might both see
    "no executing ticket" and both enqueue jobs.

    Usage:
        - Acquire: INSERT with lock_key="planner_tick"
        - Release: DELETE the row
        - Check: SELECT to see if lock is held
    """

    __tablename__ = "planner_locks"

    # Fixed key for the planner lock
    lock_key: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default="planner_tick",
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<PlannerLock(key={self.lock_key}, acquired={self.acquired_at})>"
