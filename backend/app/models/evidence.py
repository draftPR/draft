"""Evidence model for storing verification command results."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.ticket import Ticket


class EvidenceKind(str, Enum):
    """Enum representing the kind of evidence."""

    COMMAND_LOG = "command_log"
    TEST_REPORT = "test_report"


class Evidence(Base):
    """Evidence model representing verification command execution results."""

    __tablename__ = "evidence"

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
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=EvidenceKind.COMMAND_LOG.value,
    )
    command: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    exit_code: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    stdout_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    stderr_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="evidence")
    job: Mapped["Job"] = relationship("Job", back_populates="evidence")

    @property
    def kind_enum(self) -> EvidenceKind:
        """Get the kind as an EvidenceKind enum."""
        return EvidenceKind(self.kind)

    @property
    def succeeded(self) -> bool:
        """Check if the command succeeded (exit code 0)."""
        return self.exit_code == 0

    def __repr__(self) -> str:
        return f"<Evidence(id={self.id}, command={self.command[:30]}..., exit_code={self.exit_code})>"

