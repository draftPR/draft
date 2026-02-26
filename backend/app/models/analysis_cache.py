"""AnalysisCache model for caching codebase analysis results."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalysisCache(Base):
    """Cache table for codebase analysis results.

    This provides idempotency for expensive LLM-based codebase analysis.
    Entries expire after a configurable TTL (default 10 minutes).

    The cache key is a hash of:
    - Repository root path
    - Focus areas (sorted)

    This allows repeated analysis requests within the TTL window to
    return cached results without making expensive LLM calls.
    """

    __tablename__ = "analysis_cache"

    id: Mapped[str] = mapped_column(
        String(64),  # SHA256 hash (32 hex chars, but allowing extra)
        primary_key=True,
    )
    result_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JSON-serialized analysis result",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        doc="When this cache entry expires",
    )

    def __repr__(self) -> str:
        return f"<AnalysisCache(id={self.id}, expires_at={self.expires_at})>"
