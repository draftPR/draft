"""Agent memory service for UDAR conversation history.

This service manages compressed conversation checkpoints for the UDAR agent.
Instead of storing full LLM conversation history (expensive), it stores
only summaries and metadata (lean storage optimization).
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_conversation_history import AgentConversationHistory


class AgentMemoryService:
    """Manages conversation history and checkpoints for UDAR agent.

    COST OPTIMIZATION: Stores summaries, not full messages.
    """

    def __init__(self, db: AsyncSession):
        """Initialize memory service.

        Args:
            db: Async database session
        """
        self.db = db

    async def save_checkpoint(
        self,
        goal_id: str,
        checkpoint_id: str,
        state: dict[str, Any],
    ) -> None:
        """Save agent state to database (COMPRESSED).

        Only stores summary + metadata, not full LLM responses.
        This keeps storage lean while preserving essential context.

        Args:
            goal_id: Goal this checkpoint belongs to
            checkpoint_id: Unique checkpoint identifier
            state: UDAR state dict to checkpoint
        """
        # Extract only essential data (not full messages)
        summary = {
            "tickets_proposed": len(state.get("proposed_tickets", [])),
            "tickets_validated": len(state.get("validated_tickets", [])),
            "reasoning_summary": state.get("reasoning", "")[:500],  # Cap at 500 chars
            "phase": state.get("phase", "unknown"),
            "iteration": state.get("iteration", 0),
            "llm_calls_made": state.get("llm_calls_made", 0),
            "trigger": state.get("trigger", "unknown"),
        }

        # Check if checkpoint already exists
        existing = await self.db.execute(
            select(AgentConversationHistory).where(
                AgentConversationHistory.goal_id == goal_id,
                AgentConversationHistory.checkpoint_id == checkpoint_id,
            )
        )
        existing_checkpoint = existing.scalar_one_or_none()

        if existing_checkpoint:
            # Update existing checkpoint
            existing_checkpoint.metadata_json = json.dumps(summary)
            existing_checkpoint.updated_at = datetime.utcnow()
        else:
            # Create new checkpoint
            history = AgentConversationHistory(
                goal_id=goal_id,
                checkpoint_id=checkpoint_id,
                messages_json=json.dumps([]),  # Empty, don't store full messages
                metadata_json=json.dumps(summary),
            )
            self.db.add(history)

        await self.db.commit()

    async def load_checkpoint(self, goal_id: str) -> dict[str, Any] | None:
        """Load most recent checkpoint summary (not full history).

        Args:
            goal_id: Goal to load checkpoint for

        Returns:
            Checkpoint summary dict, or None if no checkpoint exists
        """
        result = await self.db.execute(
            select(AgentConversationHistory)
            .where(AgentConversationHistory.goal_id == goal_id)
            .order_by(AgentConversationHistory.created_at.desc())
            .limit(1)
        )
        history = result.scalar_one_or_none()

        if history:
            # Return summary only, agent doesn't need full history
            return json.loads(history.metadata_json)

        return None

    async def list_checkpoints(
        self,
        goal_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List recent checkpoints for a goal.

        Args:
            goal_id: Goal to list checkpoints for
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoint dicts with metadata
        """
        result = await self.db.execute(
            select(AgentConversationHistory)
            .where(AgentConversationHistory.goal_id == goal_id)
            .order_by(AgentConversationHistory.created_at.desc())
            .limit(limit)
        )
        checkpoints = result.scalars().all()

        return [
            {
                "id": checkpoint.id,
                "checkpoint_id": checkpoint.checkpoint_id,
                "created_at": checkpoint.created_at.isoformat(),
                "metadata": json.loads(checkpoint.metadata_json),
            }
            for checkpoint in checkpoints
        ]

    async def cleanup_old_checkpoints(self, days: int = 30) -> int:
        """Delete checkpoints older than N days to save storage.

        Args:
            days: Age threshold in days

        Returns:
            Number of checkpoints deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.db.execute(
            delete(AgentConversationHistory).where(
                AgentConversationHistory.created_at < cutoff
            )
        )
        deleted_count = result.rowcount

        await self.db.commit()

        return deleted_count

    async def delete_checkpoints_for_goal(self, goal_id: str) -> int:
        """Delete all checkpoints for a goal.

        Args:
            goal_id: Goal to delete checkpoints for

        Returns:
            Number of checkpoints deleted
        """
        result = await self.db.execute(
            delete(AgentConversationHistory).where(
                AgentConversationHistory.goal_id == goal_id
            )
        )
        deleted_count = result.rowcount

        await self.db.commit()

        return deleted_count

    async def get_goal_summary(self, goal_id: str) -> dict[str, Any]:
        """Get summary of agent activity for a goal.

        Args:
            goal_id: Goal to summarize

        Returns:
            Summary dict with aggregated statistics
        """
        result = await self.db.execute(
            select(AgentConversationHistory).where(
                AgentConversationHistory.goal_id == goal_id
            )
        )
        checkpoints = result.scalars().all()

        if not checkpoints:
            return {
                "goal_id": goal_id,
                "checkpoint_count": 0,
                "total_llm_calls": 0,
                "total_tickets_proposed": 0,
                "first_checkpoint": None,
                "last_checkpoint": None,
            }

        # Aggregate statistics
        total_llm_calls = 0
        total_tickets_proposed = 0

        for checkpoint in checkpoints:
            metadata = json.loads(checkpoint.metadata_json)
            total_llm_calls += metadata.get("llm_calls_made", 0)
            total_tickets_proposed += metadata.get("tickets_proposed", 0)

        return {
            "goal_id": goal_id,
            "checkpoint_count": len(checkpoints),
            "total_llm_calls": total_llm_calls,
            "total_tickets_proposed": total_tickets_proposed,
            "first_checkpoint": checkpoints[-1].created_at.isoformat(),
            "last_checkpoint": checkpoints[0].created_at.isoformat(),
        }
