"""SQLite-backed rate limit entry model (replaces Redis sorted sets)."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateLimitEntry(Base):
    """A rate limit cost entry.

    Replaces Redis sorted sets. Entries are cleaned up inline
    (DELETE WHERE expires_at < now) before checking budget.
    """

    __tablename__ = "rate_limit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recorded_at: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<RateLimitEntry(key={self.client_key}, cost={self.cost})>"
