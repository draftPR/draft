"""Job model for tracking long-running task executions."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.evidence import Evidence
    from app.models.normalized_log import NormalizedLogEntry
    from app.models.revision import Revision
    from app.models.ticket import Ticket


class JobKind(StrEnum):
    """Enum representing the kind of job."""

    EXECUTE = "execute"
    VERIFY = "verify"
    RESUME = "resume"  # Resume after interactive (human) completion


class JobStatus(StrEnum):
    """Enum representing the status of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class Job(Base):
    """Job model representing a long-running task execution.

    IMPORTANT: Jobs are scoped by board_id for permission enforcement.
    """

    __tablename__ = "jobs"

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
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=JobStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    exit_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    log_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # For jobs triggered by review feedback, tracks which revision is being addressed
    source_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Session ID for executor session resume (e.g. Claude --resume)
    session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    # Health monitoring fields
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    timeout_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Relationships
    board: Mapped["Board | None"] = relationship("Board", back_populates="jobs")
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="jobs")
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Evidence.created_at.desc()",
    )
    # The revision created by this job (via Revision.job_id -> Job.id)
    revision: Mapped["Revision | None"] = relationship(
        "Revision",
        back_populates="job",
        uselist=False,
        foreign_keys="Revision.job_id",
    )
    # For jobs triggered by review, the revision being addressed
    source_revision: Mapped["Revision | None"] = relationship(
        "Revision",
        foreign_keys="Job.source_revision_id",
        viewonly=True,  # Don't allow writes through this relationship
    )
    # Normalized log entries for this job
    normalized_logs: Mapped[list["NormalizedLogEntry"]] = relationship(
        "NormalizedLogEntry",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="NormalizedLogEntry.sequence",
    )

    @property
    def kind_enum(self) -> JobKind:
        """Get the kind as a JobKind enum."""
        return JobKind(self.kind)

    @property
    def status_enum(self) -> JobStatus:
        """Get the status as a JobStatus enum."""
        return JobStatus(self.status)

    def __repr__(self) -> str:
        return f"<Job(id={self.id}, kind={self.kind}, status={self.status})>"
