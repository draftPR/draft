"""Merge checklist model for tracking merge readiness."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.goal import Goal


class MergeChecklist(Base):
    """Tracks merge readiness for a goal's tickets.

    Combines automatic checks (tests, cost) and manual checks (review, security).
    """

    __tablename__ = "merge_checklists"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    goal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Auto-checks (computed from system state)
    all_tests_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    total_files_changed: Mapped[int] = mapped_column(Integer, default=0)
    total_lines_changed: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_exceeded: Mapped[bool] = mapped_column(Boolean, default=False)

    # Manual checks (require human confirmation)
    code_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    no_sensitive_data: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_plan_understood: Mapped[bool] = mapped_column(Boolean, default=False)
    documentation_updated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Rollback plan
    rollback_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(
        String(20),
        default="low"  # low, medium, high
    )

    # Status
    ready_to_merge: Mapped[bool] = mapped_column(Boolean, default=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="merge_checklist")

    def __repr__(self) -> str:
        return f"<MergeChecklist(id={self.id}, goal_id={self.goal_id}, ready={self.ready_to_merge})>"

    def is_ready_to_merge(self) -> bool:
        """Check if all conditions are met for merging."""
        # All auto-checks must pass
        if not self.all_tests_passed:
            return False
        if self.budget_exceeded:
            return False

        # All manual checks must be confirmed
        if not (self.code_reviewed and self.no_sensitive_data and self.rollback_plan_understood):
            return False

        return True
