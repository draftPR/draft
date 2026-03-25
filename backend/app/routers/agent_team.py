"""API router for agent team configuration.

Provides CRUD endpoints for managing the multi-agent team composition
on a board, plus the role catalog for the team builder UI.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.agent_team import AgentTeam, AgentTeamMember
from app.services.agent_catalog import (
    get_preset,
    get_preset_names,
    get_role,
    get_role_catalog,
)

router = APIRouter(tags=["agent-team"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RoleCatalogItem(BaseModel):
    role: str
    display_name: str
    description: str
    default_prompt: str
    receive_mode: str
    is_required: bool
    category: str
    icon: str


class TeamMemberResponse(BaseModel):
    id: str
    role: str
    display_name: str
    executor_type: str
    behavior_prompt: str | None
    receive_mode: str
    is_required: bool
    sort_order: int

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    id: str
    board_id: str
    name: str
    is_active: bool
    members: list[TeamMemberResponse]

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    role: str
    display_name: str | None = None
    executor_type: str = "claude"
    behavior_prompt: str | None = None


class UpdateMemberRequest(BaseModel):
    display_name: str | None = None
    executor_type: str | None = None
    behavior_prompt: str | None = None
    sort_order: int | None = None


class UpdateTeamRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class ApplyPresetRequest(BaseModel):
    preset: str  # "default", "duo", "full_stack", "ml_pipeline", "security_audit"


# ---------------------------------------------------------------------------
# Catalog endpoints
# ---------------------------------------------------------------------------


@router.get("/agent-catalog", response_model=list[RoleCatalogItem])
async def list_role_catalog():
    """List all available agent roles for the team builder."""
    return [
        RoleCatalogItem(
            role=r.role,
            display_name=r.display_name,
            description=r.description,
            default_prompt=r.default_prompt,
            receive_mode=r.receive_mode,
            is_required=r.is_required,
            category=r.category,
            icon=r.icon,
        )
        for r in get_role_catalog()
    ]


@router.get("/agent-presets", response_model=list[str])
async def list_presets():
    """List available team preset names."""
    return get_preset_names()


# ---------------------------------------------------------------------------
# Team CRUD (scoped to board)
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}/team", response_model=TeamResponse | None)
async def get_team(
    board_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the agent team for a board (or null if not configured)."""
    stmt = (
        select(AgentTeam)
        .where(AgentTeam.board_id == board_id)
        .options(selectinload(AgentTeam.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()
    if team is None:
        return None
    return team


@router.put("/boards/{board_id}/team", response_model=TeamResponse)
async def update_team(
    board_id: str,
    body: UpdateTeamRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update team settings (name, active state)."""
    stmt = (
        select(AgentTeam)
        .where(AgentTeam.board_id == board_id)
        .options(selectinload(AgentTeam.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if team is None:
        # Create team if it doesn't exist
        team = AgentTeam(
            id=str(uuid4()),
            board_id=board_id,
            name=body.name or "Default Team",
            is_active=body.is_active if body.is_active is not None else False,
        )
        db.add(team)
        await db.flush()
        await db.refresh(team, ["members"])
    else:
        if body.name is not None:
            team.name = body.name
        if body.is_active is not None:
            team.is_active = body.is_active

    await db.commit()
    await db.refresh(team, ["members"])
    return team


@router.post(
    "/boards/{board_id}/team/preset",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_preset(
    board_id: str,
    body: ApplyPresetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Apply a preset team composition to a board.

    Replaces all existing members with the preset's roles.
    """
    preset_roles = get_preset(body.preset)
    if preset_roles is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown preset: {body.preset}. Available: {get_preset_names()}",
        )

    # Get or create team
    stmt = (
        select(AgentTeam)
        .where(AgentTeam.board_id == board_id)
        .options(selectinload(AgentTeam.members))
    )
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if team is None:
        team = AgentTeam(
            id=str(uuid4()),
            board_id=board_id,
            name=f"{body.preset.replace('_', ' ').title()} Team",
            is_active=False,
        )
        db.add(team)
        await db.flush()
    else:
        # Remove existing members
        for member in list(team.members):
            await db.delete(member)
        await db.flush()

    # Add preset members
    for i, role_def in enumerate(preset_roles):
        member = AgentTeamMember(
            id=str(uuid4()),
            team_id=team.id,
            role=role_def.role,
            display_name=role_def.display_name,
            executor_type="claude",
            behavior_prompt=role_def.default_prompt,
            receive_mode=role_def.receive_mode,
            is_required=role_def.is_required,
            sort_order=i,
        )
        db.add(member)

    await db.commit()
    await db.refresh(team, ["members"])
    return team


# ---------------------------------------------------------------------------
# Team member CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/boards/{board_id}/team/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    board_id: str,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a member to the board's agent team."""
    # Get or create team
    stmt = select(AgentTeam).where(AgentTeam.board_id == board_id)
    result = await db.execute(stmt)
    team = result.scalar_one_or_none()

    if team is None:
        team = AgentTeam(
            id=str(uuid4()),
            board_id=board_id,
            name="Default Team",
            is_active=False,
        )
        db.add(team)
        await db.flush()

    # Look up role definition for defaults
    role_def = get_role(body.role)
    display_name = body.display_name or (
        role_def.display_name if role_def else body.role
    )
    behavior_prompt = body.behavior_prompt or (
        role_def.default_prompt if role_def else None
    )
    receive_mode = role_def.receive_mode if role_def else "mentions"
    is_required = role_def.is_required if role_def else False

    # Get next sort order
    from sqlalchemy import func

    max_order_stmt = select(func.max(AgentTeamMember.sort_order)).where(
        AgentTeamMember.team_id == team.id
    )
    max_order_result = await db.execute(max_order_stmt)
    max_order = max_order_result.scalar() or 0

    member = AgentTeamMember(
        id=str(uuid4()),
        team_id=team.id,
        role=body.role,
        display_name=display_name,
        executor_type=body.executor_type,
        behavior_prompt=behavior_prompt,
        receive_mode=receive_mode,
        is_required=is_required,
        sort_order=max_order + 1,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch(
    "/boards/{board_id}/team/members/{member_id}",
    response_model=TeamMemberResponse,
)
async def update_member(
    board_id: str,
    member_id: str,
    body: UpdateMemberRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a team member's settings."""
    stmt = select(AgentTeamMember).where(AgentTeamMember.id == member_id)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if body.display_name is not None:
        member.display_name = body.display_name
    if body.executor_type is not None:
        member.executor_type = body.executor_type
    if body.behavior_prompt is not None:
        member.behavior_prompt = body.behavior_prompt
    if body.sort_order is not None:
        member.sort_order = body.sort_order

    await db.commit()
    await db.refresh(member)
    return member


@router.delete(
    "/boards/{board_id}/team/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    board_id: str,
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the team."""
    stmt = select(AgentTeamMember).where(AgentTeamMember.id == member_id)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.is_required:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove required role: {member.role}",
        )
    await db.delete(member)
    await db.commit()


# ---------------------------------------------------------------------------
# Team session status (during execution)
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}/team/status")
async def get_team_execution_status(
    board_id: str,
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the live status of all agents executing for a ticket."""

    from app.models.agent_team import TeamAgentSession

    stmt = (
        select(TeamAgentSession)
        .where(TeamAgentSession.ticket_id == ticket_id)
        .order_by(TeamAgentSession.created_at.asc())
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    return [
        {
            "id": s.id,
            "team_member_id": s.team_member_id,
            "tmux_session_name": s.tmux_session_name,
            "status": s.status,
            "last_pulse_status": s.last_pulse_status,
            "last_pulse_summary": s.last_pulse_summary,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        }
        for s in sessions
    ]
