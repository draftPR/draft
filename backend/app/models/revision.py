"""Revision model for tracking agent code change iterations."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.job import Job
    from app.models.review_comment import ReviewComment
    from app.models.review_summary import ReviewSummary
    from app.models.ticket import Ticket


class RevisionStatus(str, Enum):
    """Enum representing the status of a revision."""

    OPEN = "open"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class Revision(Base):
    """Revision model representing one agent iteration for a ticket.

    A revision is similar to a GitHub PR snapshot - it contains:
    - A diff (stat + patch as evidence)
    - Review comments
    - A final review decision

    Only one revision per ticket can be 'open' at a time.
    When a new revision is created, previous open revision becomes 'superseded'.
    """

    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("ticket_id", "number", name="uq_revision_ticket_number"),
        UniqueConstraint("ticket_id", "job_id", name="uq_revision_ticket_job"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=RevisionStatus.OPEN.value,
        nullable=False,
        index=True,
    )
    diff_stat_evidence_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff_patch_evidence_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="revisions")
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="revision",
        foreign_keys=[job_id],
    )
    diff_stat_evidence: Mapped["Evidence | None"] = relationship(
        "Evidence",
        foreign_keys=[diff_stat_evidence_id],
    )
    diff_patch_evidence: Mapped["Evidence | None"] = relationship(
        "Evidence",
        foreign_keys=[diff_patch_evidence_id],
    )
    comments: Mapped[list["ReviewComment"]] = relationship(
        "ReviewComment",
        back_populates="revision",
        cascade="all, delete-orphan",
        order_by="ReviewComment.created_at",
    )
    review_summary: Mapped["ReviewSummary | None"] = relationship(
        "ReviewSummary",
        back_populates="revision",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def status_enum(self) -> RevisionStatus:
        """Get the status as a RevisionStatus enum."""
        return RevisionStatus(self.status)

    @property
    def unresolved_comment_count(self) -> int:
        """Get count of unresolved comments."""
        return sum(1 for c in self.comments if not c.resolved)

    def __repr__(self) -> str:
        return f"<Revision(id={self.id}, ticket_id={self.ticket_id}, number={self.number}, status={self.status})>"

