"""SQLite-backed job queue model (replaces Celery/Redis broker)."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobQueueEntry(Base):
    """A queued task for the SQLite worker to process.

    Replaces the Celery broker queue. Tasks are claimed atomically
    via UPDATE...WHERE status='pending' ORDER BY priority DESC, created_at ASC.
    """

    __tablename__ = "job_queue"
    __table_args__ = (
        Index("ix_job_queue_claim_order", "status", "priority", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<JobQueueEntry(id={self.id}, task={self.task_name}, status={self.status})>"
