"""SQLite-backed idempotency cache model (replaces Redis SETNX)."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IdempotencyEntry(Base):
    """Idempotency lock and result cache entry.

    Replaces Redis SETNX + result cache. Lock acquisition is atomic
    via INSERT OR IGNORE (rowcount == 1 means acquired).
    """

    __tablename__ = "idempotency_cache"

    cache_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    lock_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<IdempotencyEntry(key={self.cache_key[:30]}...)>"
