"""ReviewComment model for inline comments on revision diffs."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.revision import Revision


class AuthorType(StrEnum):
    """Enum representing the type of author for a review comment."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class ReviewComment(Base):
    """ReviewComment model representing inline comments on a revision diff.

    Comments are anchored using a sha1 hash of (file_path + hunk_header + line_content)
    to survive small line shifts between revisions.
    """

    __tablename__ = "review_comments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    anchor: Mapped[str] = mapped_column(
        String(40),  # sha1 hex digest (truncated to 16 chars in practice)
        nullable=False,
        index=True,
    )
    line_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    author_type: Mapped[str] = mapped_column(
        String(20),
        default=AuthorType.HUMAN.value,
        nullable=False,
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    revision: Mapped["Revision"] = relationship("Revision", back_populates="comments")

    @property
    def author_type_enum(self) -> AuthorType:
        """Get the author_type as an AuthorType enum."""
        return AuthorType(self.author_type)

    def __repr__(self) -> str:
        return f"<ReviewComment(id={self.id}, file={self.file_path}, line={self.line_number}, resolved={self.resolved})>"
