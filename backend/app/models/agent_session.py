"""Agent session model for conversation continuity.

Tracks agent sessions to enable:
- Follow-up prompts within the same conversation
- Session resume after interruptions
- Cost tracking per session
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base


class AgentSession(Base):
    """Tracks an AI agent conversation session."""
    
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id = Column(String(36), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Agent identification
    agent_type = Column(String(50), nullable=False)  # claude, amp, cursor, etc.
    agent_session_id = Column(String(255), nullable=True)  # External session ID from agent
    
    # Session state
    is_active = Column(Boolean, default=True, nullable=False)
    turn_count = Column(Integer, default=0, nullable=False)
    
    # Token tracking for cost calculation
    total_input_tokens = Column(Integer, default=0, nullable=False)
    total_output_tokens = Column(Integer, default=0, nullable=False)
    estimated_cost_usd = Column(Float, default=0.0, nullable=False)
    
    # Last message for context
    last_prompt = Column(Text, nullable=True)
    last_response_summary = Column(Text, nullable=True)
    
    # Metadata
    metadata_ = Column("metadata", JSON, nullable=True)  # Agent-specific metadata
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    ticket = relationship("Ticket", back_populates="agent_sessions")
    messages = relationship("AgentMessage", back_populates="session", cascade="all, delete-orphan")

    def add_turn(self, input_tokens: int, output_tokens: int, cost: float = 0.0):
        """Record a conversation turn."""
        self.turn_count += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.estimated_cost_usd += cost
        self.updated_at = datetime.utcnow()
    
    def end_session(self):
        """Mark session as ended."""
        self.is_active = False
        self.ended_at = datetime.utcnow()


class AgentMessage(Base):
    """Individual message in an agent session."""
    
    __tablename__ = "agent_messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    
    # Token counts
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    
    # Tool use tracking
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(Text, nullable=True)
    
    # Metadata
    metadata_ = Column("metadata", JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("AgentSession", back_populates="messages")
