"""ReviewSummary model for overall review decisions on revisions."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.revision import Revision


class ReviewDecision(StrEnum):
    """Enum representing the review decision."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ReviewSummary(Base):
    """ReviewSummary model representing the overall review decision for a revision.

    Only one ReviewSummary per revision is allowed.
    """

    __tablename__ = "review_summaries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    decision: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    revision: Mapped["Revision"] = relationship(
        "Revision", back_populates="review_summary"
    )

    @property
    def decision_enum(self) -> ReviewDecision:
        """Get the decision as a ReviewDecision enum."""
        return ReviewDecision(self.decision)

    def __repr__(self) -> str:
        return f"<ReviewSummary(id={self.id}, revision_id={self.revision_id}, decision={self.decision})>"
