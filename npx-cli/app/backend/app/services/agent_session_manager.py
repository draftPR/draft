"""Enhanced agent session management with database persistence and cost tracking.

This module provides database-backed session management for:
- Conversation continuity (session resume)
- Cost tracking per session
- Multi-agent support via the agent registry
"""

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_session import AgentMessage, AgentSession
from app.services.agent_registry import (
    AGENT_REGISTRY,
    AgentType,
)
from app.services.cost_tracking_service import CostTrackingService, TokenUsage

logger = logging.getLogger(__name__)


class AgentSessionManager:
    """Manages agent sessions with database persistence and cost tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.cost_service = CostTrackingService()

    async def create_session(
        self,
        ticket_id: str,
        agent_type: str,
        job_id: str | None = None,
        external_session_id: str | None = None,
        metadata: dict | None = None,
    ) -> AgentSession:
        """Create a new agent session.

        Args:
            ticket_id: The ticket this session is for
            agent_type: Type of agent (claude, amp, cursor, etc.)
            job_id: Optional job ID
            external_session_id: Optional external session ID from the agent
            metadata: Optional metadata dict

        Returns:
            The created AgentSession
        """
        session = AgentSession(
            id=str(uuid4()),
            ticket_id=ticket_id,
            job_id=job_id,
            agent_type=agent_type,
            agent_session_id=external_session_id,
            is_active=True,
            turn_count=0,
            total_input_tokens=0,
            total_output_tokens=0,
            estimated_cost_usd=0.0,
            metadata_=metadata,
        )

        self.db.add(session)
        await self.db.flush()

        logger.info(
            f"Created agent session {session.id[:8]}... for ticket {ticket_id[:8]}... "
            f"using {agent_type}"
        )

        return session

    async def get_active_session(
        self,
        ticket_id: str,
        agent_type: str | None = None,
    ) -> AgentSession | None:
        """Get the active session for a ticket.

        Args:
            ticket_id: The ticket to get session for
            agent_type: Optional agent type filter

        Returns:
            The active AgentSession if one exists
        """
        query = select(AgentSession).where(
            AgentSession.ticket_id == ticket_id, AgentSession.is_active
        )

        if agent_type:
            query = query.where(AgentSession.agent_type == agent_type)

        query = query.order_by(AgentSession.updated_at.desc())

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_session(
        self,
        ticket_id: str,
        agent_type: str,
        job_id: str | None = None,
    ) -> tuple[AgentSession, bool]:
        """Get existing active session or create new one.

        Args:
            ticket_id: The ticket ID
            agent_type: The agent type
            job_id: Optional job ID

        Returns:
            Tuple of (session, is_new)
        """
        existing = await self.get_active_session(ticket_id, agent_type)
        if existing:
            return existing, False

        session = await self.create_session(
            ticket_id=ticket_id,
            agent_type=agent_type,
            job_id=job_id,
        )
        return session, True

    async def record_turn(
        self,
        session_id: str,
        prompt: str,
        response: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: str | None = None,
    ) -> tuple[AgentSession, float]:
        """Record a conversation turn with cost tracking.

        Args:
            session_id: The session ID
            prompt: The user prompt
            response: The assistant response
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            tool_name: Optional tool that was used
            tool_input: Optional tool input
            tool_output: Optional tool output

        Returns:
            Tuple of (updated_session, turn_cost)
        """
        result = await self.db.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Calculate cost
        try:
            agent_type = AgentType(session.agent_type)
            config = AGENT_REGISTRY.get(agent_type)
            if config and config.cost_per_1k_input and config.cost_per_1k_output:
                usage = TokenUsage(
                    input_tokens=input_tokens, output_tokens=output_tokens
                )
                turn_cost = self.cost_service.calculate_cost(
                    usage, config.cost_per_1k_input, config.cost_per_1k_output
                )
            else:
                turn_cost = 0.0
        except (ValueError, KeyError):
            turn_cost = 0.0

        # Update session
        session.turn_count += 1
        session.total_input_tokens += input_tokens
        session.total_output_tokens += output_tokens
        session.estimated_cost_usd += turn_cost
        session.last_prompt = prompt[:2000] if prompt else None  # Truncate for storage
        session.last_response_summary = (
            response[:500] if response else None
        )  # Summary only
        session.updated_at = datetime.utcnow()

        # Create message record for user prompt
        user_message = AgentMessage(
            id=str(uuid4()),
            session_id=session_id,
            role="user",
            content=prompt,
            input_tokens=input_tokens,
            output_tokens=0,
        )
        self.db.add(user_message)

        # Create message record for assistant response
        assistant_message = AgentMessage(
            id=str(uuid4()),
            session_id=session_id,
            role="assistant",
            content=response,
            input_tokens=0,
            output_tokens=output_tokens,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
        )
        self.db.add(assistant_message)

        await self.db.flush()

        logger.info(
            f"Recorded turn {session.turn_count} for session {session_id[:8]}...: "
            f"{input_tokens} in, {output_tokens} out, ${turn_cost:.4f}"
        )

        return session, turn_cost

    async def end_session(self, session_id: str) -> AgentSession:
        """End a session and mark it inactive.

        Args:
            session_id: The session ID

        Returns:
            The ended session
        """
        result = await self.db.execute(
            select(AgentSession).where(AgentSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        session.is_active = False
        session.ended_at = datetime.utcnow()

        await self.db.flush()

        logger.info(
            f"Ended session {session_id[:8]}...: "
            f"{session.turn_count} turns, ${session.estimated_cost_usd:.4f} total"
        )

        return session

    async def get_session_history(
        self,
        ticket_id: str,
        limit: int = 10,
    ) -> list[AgentSession]:
        """Get session history for a ticket.

        Args:
            ticket_id: The ticket ID
            limit: Maximum number of sessions to return

        Returns:
            List of sessions ordered by most recent first
        """
        result = await self.db.execute(
            select(AgentSession)
            .where(AgentSession.ticket_id == ticket_id)
            .order_by(AgentSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_ticket_total_cost(self, ticket_id: str) -> float:
        """Get total cost across all sessions for a ticket.

        Args:
            ticket_id: The ticket ID

        Returns:
            Total cost in USD
        """
        sessions = await self.get_session_history(ticket_id, limit=1000)
        return sum(s.estimated_cost_usd for s in sessions)


def get_resumable_session_args(
    session: AgentSession | None,
    agent_type: str,
) -> dict:
    """Get command-line args for resuming a session if supported.

    Args:
        session: Optional existing session
        agent_type: The agent type

    Returns:
        Dict of args to add to command (empty if no resume support)
    """
    if not session or not session.agent_session_id:
        return {}

    try:
        agent_enum = AgentType(agent_type)
        config = AGENT_REGISTRY.get(agent_enum)

        if config and config.supports_session_resume:
            if agent_enum == AgentType.CLAUDE:
                return {"--resume": session.agent_session_id}
            elif agent_enum == AgentType.AMP:
                return {"--thread": session.agent_session_id}

    except (ValueError, KeyError):
        pass

    return {}
