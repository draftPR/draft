"""Job model for tracking long-running task executions."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.ticket import Ticket


class JobKind(str, Enum):
    """Enum representing the kind of job."""

    EXECUTE = "execute"
    VERIFY = "verify"
    RESUME = "resume"  # Resume after interactive (human) completion


class JobStatus(str, Enum):
    """Enum representing the status of a job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class Job(Base):
    """Job model representing a long-running task execution."""

    __tablename__ = "jobs"

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

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="jobs")
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Evidence.created_at.desc()",
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
