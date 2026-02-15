"""SQLite-backed key-value store model (replaces Redis GET/SET)."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KVStoreEntry(Base):
    """Generic key-value store with optional TTL.

    Replaces Redis GET/SET for queued messages and follow-up prompts.
    Expired entries are cleaned up inline on access.
    """

    __tablename__ = "kv_store"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<KVStoreEntry(key={self.key[:30]}...)>"
