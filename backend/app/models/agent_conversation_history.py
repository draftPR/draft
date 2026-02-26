"""Agent conversation history model for UDAR agent memory.

Stores compressed checkpoints (summaries, not full messages) to support
UDAR agent state persistence.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class AgentConversationHistory(Base):
    """Agent conversation history for UDAR memory.

    This model stores compressed conversation checkpoints for the UDAR agent.
    Instead of storing full LLM conversation history (expensive), it stores
    only summaries and metadata (lean storage).

    Attributes:
        id: Unique identifier (ULID)
        goal_id: Goal this conversation belongs to
        checkpoint_id: Unique checkpoint identifier
        messages_json: Empty by default (lean storage optimization)
        metadata_json: Compressed summary (tickets proposed, reasoning summary, etc.)
        created_at: When checkpoint was created
        updated_at: When checkpoint was last updated
        goal: Related Goal object
    """

    __tablename__ = "agent_conversation_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    goal_id = Column(
        String(36),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checkpoint_id = Column(String(100), nullable=False)
    messages_json = Column(Text, nullable=True)  # Empty by default
    metadata_json = Column(Text, nullable=False)  # Compressed summary
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    goal = relationship("Goal", back_populates="agent_conversation_history")

    def __repr__(self) -> str:
        """String representation."""
        return f"<AgentConversationHistory(id={self.id}, goal_id={self.goal_id}, checkpoint={self.checkpoint_id})>"
