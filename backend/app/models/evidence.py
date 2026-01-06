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
    """Enum representing the kind of evidence.

    Evidence types for execution:
    - EXECUTOR_STDOUT: stdout from executor CLI (Claude/Cursor)
    - EXECUTOR_STDERR: stderr from executor CLI
    - GIT_DIFF_STAT: output of `git diff --stat`
    - GIT_DIFF_PATCH: full git diff patch

    Evidence types for verification:
    - VERIFY_STDOUT: stdout from verification command
    - VERIFY_STDERR: stderr from verification command

    Legacy types (kept for backwards compatibility):
    - COMMAND_LOG: generic command output
    - TEST_REPORT: test framework report
    """

    # Executor evidence
    EXECUTOR_STDOUT = "executor_stdout"
    EXECUTOR_STDERR = "executor_stderr"

    # Git diff evidence
    GIT_DIFF_STAT = "git_diff_stat"
    GIT_DIFF_PATCH = "git_diff_patch"

    # Verification evidence
    VERIFY_STDOUT = "verify_stdout"
    VERIFY_STDERR = "verify_stderr"

    # Legacy types (backwards compatibility)
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

