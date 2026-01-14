"""AI Agent management API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_session import AgentSession, AgentMessage
from app.services.agent_registry import (
    AgentType,
    AGENT_REGISTRY,
    agent_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


# ============================================================================
# Response Models
# ============================================================================

class AgentInfo(BaseModel):
    """Information about an AI agent."""
    type: str
    name: str
    available: bool
    supports_yolo: bool = False
    supports_session_resume: bool = False
    supports_mcp: bool = False
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None
    description: str = ""


class AgentListResponse(BaseModel):
    """List of available agents."""
    agents: list[AgentInfo]
    default_agent: str = "claude"


class SessionInfo(BaseModel):
    """Agent session information."""
    id: str
    ticket_id: str
    agent_type: str
    agent_session_id: Optional[str] = None
    is_active: bool
    turn_count: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    last_prompt: Optional[str] = None
    created_at: str
    updated_at: str
    ended_at: Optional[str] = None


class SessionListResponse(BaseModel):
    """List of sessions for a ticket."""
    sessions: list[SessionInfo]
    total: int


class MessageInfo(BaseModel):
    """Agent message information."""
    id: str
    role: str
    content: str
    input_tokens: int
    output_tokens: int
    tool_name: Optional[str] = None
    created_at: str


class SessionDetailResponse(BaseModel):
    """Detailed session information with messages."""
    session: SessionInfo
    messages: list[MessageInfo]


# ============================================================================
# Agent Descriptions
# ============================================================================

AGENT_DESCRIPTIONS = {
    AgentType.CLAUDE: "Anthropic's Claude Code CLI - best for complex reasoning and code generation",
    AgentType.CURSOR: "Cursor IDE's agent mode - interactive, opens editor",
    AgentType.AMP: "Sourcegraph's Amp agent - fast, good for quick fixes",
    AgentType.AIDER: "Open-source coding assistant - free, supports multiple models",
    AgentType.CODEX: "OpenAI's Codex - specialized for code completion",
    AgentType.GEMINI: "Google's Gemini CLI - multimodal capabilities",
}

AGENT_DISPLAY_NAMES = {
    AgentType.CLAUDE: "Claude Code",
    AgentType.CURSOR: "Cursor Agent",
    AgentType.AMP: "Amp",
    AgentType.AIDER: "Aider",
    AgentType.CODEX: "Codex",
    AgentType.GEMINI: "Gemini",
}


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """List all known AI agents and their availability."""
    agents = []
    
    for agent_type in AgentType:
        config = AGENT_REGISTRY.get(agent_type)
        if not config:
            continue
        
        executor = agent_registry.get_executor(agent_type)
        is_available = executor.is_available() if executor else False
        
        agents.append(AgentInfo(
            type=agent_type.value,
            name=AGENT_DISPLAY_NAMES.get(agent_type, agent_type.value),
            available=is_available,
            supports_yolo=config.supports_yolo,
            supports_session_resume=config.supports_session_resume,
            supports_mcp=config.supports_mcp,
            cost_per_1k_input=config.cost_per_1k_input,
            cost_per_1k_output=config.cost_per_1k_output,
            description=AGENT_DESCRIPTIONS.get(agent_type, ""),
        ))
    
    # Sort: available first, then by name
    agents.sort(key=lambda a: (not a.available, a.name))
    
    return AgentListResponse(
        agents=agents,
        default_agent="claude"
    )


@router.get("/available", response_model=list[str])
async def list_available_agents() -> list[str]:
    """List only the agents available on this system."""
    available = agent_registry.get_available_agents()
    return [a.value for a in available]


@router.get("/{agent_type}", response_model=AgentInfo)
async def get_agent(agent_type: str) -> AgentInfo:
    """Get detailed information about a specific agent."""
    try:
        agent_enum = AgentType(agent_type)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown agent type: {agent_type}")
    
    config = AGENT_REGISTRY.get(agent_enum)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent not configured: {agent_type}")
    
    executor = agent_registry.get_executor(agent_enum)
    is_available = executor.is_available() if executor else False
    
    return AgentInfo(
        type=agent_enum.value,
        name=AGENT_DISPLAY_NAMES.get(agent_enum, agent_enum.value),
        available=is_available,
        supports_yolo=config.supports_yolo,
        supports_session_resume=config.supports_session_resume,
        supports_mcp=config.supports_mcp,
        cost_per_1k_input=config.cost_per_1k_input,
        cost_per_1k_output=config.cost_per_1k_output,
        description=AGENT_DESCRIPTIONS.get(agent_enum, ""),
    )


@router.get("/sessions/ticket/{ticket_id}", response_model=SessionListResponse)
async def list_ticket_sessions(
    ticket_id: str,
    include_ended: bool = Query(False, description="Include ended sessions"),
    db: AsyncSession = Depends(get_db)
) -> SessionListResponse:
    """List all agent sessions for a ticket."""
    query = select(AgentSession).where(AgentSession.ticket_id == ticket_id)
    
    if not include_ended:
        query = query.where(AgentSession.is_active == True)
    
    query = query.order_by(AgentSession.created_at.desc())
    
    result = await db.execute(query)
    sessions = result.scalars().all()
    
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.id,
                ticket_id=s.ticket_id,
                agent_type=s.agent_type,
                agent_session_id=s.agent_session_id,
                is_active=s.is_active,
                turn_count=s.turn_count,
                total_input_tokens=s.total_input_tokens,
                total_output_tokens=s.total_output_tokens,
                estimated_cost_usd=s.estimated_cost_usd,
                last_prompt=s.last_prompt[:200] if s.last_prompt else None,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                ended_at=s.ended_at.isoformat() if s.ended_at else None,
            )
            for s in sessions
        ],
        total=len(sessions)
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
) -> SessionDetailResponse:
    """Get detailed session information with messages."""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Load messages
    msg_result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at)
    )
    messages = msg_result.scalars().all()
    
    return SessionDetailResponse(
        session=SessionInfo(
            id=session.id,
            ticket_id=session.ticket_id,
            agent_type=session.agent_type,
            agent_session_id=session.agent_session_id,
            is_active=session.is_active,
            turn_count=session.turn_count,
            total_input_tokens=session.total_input_tokens,
            total_output_tokens=session.total_output_tokens,
            estimated_cost_usd=session.estimated_cost_usd,
            last_prompt=session.last_prompt,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
        ),
        messages=[
            MessageInfo(
                id=m.id,
                role=m.role,
                content=m.content,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                tool_name=m.tool_name,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ]
    )


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """End an active session."""
    result = await db.execute(
        select(AgentSession).where(AgentSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session already ended")
    
    session.end_session()
    await db.commit()
    
    return {"message": "Session ended", "session_id": session_id}
