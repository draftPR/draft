"""Cost budget model for tracking spending limits."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class CostBudget(Base):
    """Budget configuration for cost tracking."""

    __tablename__ = "cost_budgets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    goal_id = Column(String(36), ForeignKey("goals.id", ondelete="CASCADE"), nullable=True, index=True)

    # Budget limits (None = unlimited)
    daily_budget = Column(Float, nullable=True)
    weekly_budget = Column(Float, nullable=True)
    monthly_budget = Column(Float, nullable=True)
    total_budget = Column(Float, nullable=True)

    # Alert settings
    warning_threshold = Column(Float, default=0.8, nullable=False)  # 80% by default
    pause_on_exceed = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    goal = relationship("Goal", back_populates="budget")
