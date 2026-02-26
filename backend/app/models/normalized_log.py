"""Database models for normalized log entries."""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base


class LogEntryType(enum.StrEnum):
    """Semantic types for normalized log entries."""

    THINKING = "thinking"
    ASSISTANT_MESSAGE = "assistant_message"  # Agent's response/reasoning
    FILE_EDIT = "file_edit"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    COMMAND_RUN = "command_run"
    TOOL_CALL = "tool_call"
    ERROR = "error"
    USER_MESSAGE = "user_message"
    SYSTEM_MESSAGE = "system_message"
    LOADING = "loading"
    TODO_LIST = "todo_list"  # Agent's todo/task list

    # UDAR agent entry types
    AGENT_UNDERSTANDING = "agent_understanding"  # Context gathered in Understand phase
    AGENT_DECISION = "agent_decision"  # LLM reasoning in Decide phase
    AGENT_VALIDATION = "agent_validation"  # Validation results in Validate phase
    AGENT_TOOL_CALL = "agent_tool_call"  # Tool invocations (deterministic)


class NormalizedLogEntry(Base):
    """Structured, semantic log entry parsed from raw agent output."""

    __tablename__ = "normalized_log_entries"

    id = Column(
        String(36), primary_key=True, default=lambda: str(__import__("uuid").uuid4())
    )

    # Foreign key to job
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    job = relationship("Job", back_populates="normalized_logs")

    # Sequence number for ordering
    sequence = Column(Integer, nullable=False)

    # Timestamp of the entry
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Entry type (semantic category)
    entry_type = Column(Enum(LogEntryType), nullable=False, index=True)

    # Text content (can be markdown, code, etc.)
    content = Column(Text, nullable=False)

    # Structured metadata (JSON)
    # Examples:
    # - file_edit: {"file_path": "app/auth.py", "diff": "...", "language": "python"}
    # - command_run: {"command": "pytest", "exit_code": 0, "output": "..."}
    # - tool_call: {"tool_name": "web_search", "args": {...}, "result": {...}}
    # - error: {"error_type": "SyntaxError", "traceback": "..."}
    # Note: "metadata" is reserved in SQLAlchemy, so using "entry_metadata"
    entry_metadata = Column(JSON, nullable=True)

    # Display flags
    collapsed = Column(Boolean, default=False)  # Start collapsed?
    highlight = Column(Boolean, default=False)  # Highlight in UI?

    __table_args__ = (
        Index("ix_normalized_log_entries_job_sequence", "job_id", "sequence"),
    )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "entry_type": self.entry_type.value if self.entry_type else None,
            "content": self.content,
            "metadata": self.entry_metadata or {},  # Return as "metadata" for frontend
            "collapsed": self.collapsed,
            "highlight": self.highlight,
        }
