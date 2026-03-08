"""Router for project settings (DB-backed via Board.config)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.board import Board
from app.services.config_service import DraftConfig, deep_merge_dicts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class ExecuteConfigUpdate(BaseModel):
    """Execute configuration update model."""

    timeout: int | None = None
    preferred_executor: str | None = None
    executor_model: str | None = None


class SettingsUpdate(BaseModel):
    """Global settings update model."""

    execute_config: ExecuteConfigUpdate | None = None


class SettingsResponse(BaseModel):
    """Global settings response model."""

    execute_config: dict[str, Any]
    board_id: str


# --- Planner config models ---


class PlannerConfigResponse(BaseModel):
    """Planner configuration response."""

    model: str
    agent_path: str
    timeout: int
    preferred_executor: str  # From execute_config, so frontend knows the CLI type


class PlannerConfigUpdate(BaseModel):
    """Planner configuration update."""

    model: str | None = None
    agent_path: str | None = None


class PlannerHealthResponse(BaseModel):
    """Planner health check response."""

    status: str  # "online" | "offline"
    model: str
    error: str | None = None


async def _resolve_board(db: AsyncSession, board_id: str | None) -> Board:
    """Resolve a board by ID, or fall back to the first board."""
    if board_id:
        result = await db.execute(select(Board).where(Board.id == board_id))
        board = result.scalar_one_or_none()
        if not board:
            raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
        return board

    result = await db.execute(select(Board).limit(1))
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(
            status_code=400,
            detail="No boards exist. Create a board first.",
        )
    return board


@router.get("", response_model=SettingsResponse)
async def get_global_settings(
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get execute settings from board config (DB).

    Returns:
        Current execute_config from the board's config.
    """
    board = await _resolve_board(db, board_id)
    config = DraftConfig.from_board_config(board.config)

    return SettingsResponse(
        execute_config={
            "timeout": config.execute_config.timeout,
            "preferred_executor": config.execute_config.preferred_executor,
            "executor_model": config.execute_config.executor_model,
        },
        board_id=board.id,
    )


@router.put("", response_model=SettingsResponse)
async def update_global_settings(
    data: SettingsUpdate,
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Update execute settings in board config (DB).

    Args:
        data: Settings to update (partial update supported)

    Returns:
        Updated settings
    """
    board = await _resolve_board(db, board_id)

    update_dict: dict[str, Any] = {}
    if data.execute_config:
        ec: dict[str, Any] = {}
        if data.execute_config.timeout is not None:
            ec["timeout"] = data.execute_config.timeout
        if data.execute_config.preferred_executor is not None:
            ec["preferred_executor"] = data.execute_config.preferred_executor
        if data.execute_config.executor_model is not None:
            ec["executor_model"] = data.execute_config.executor_model
        if ec:
            update_dict["execute_config"] = ec

    if update_dict:
        existing = board.config or {}
        board.config = deep_merge_dicts(existing, update_dict)
        await db.commit()
        await db.refresh(board)

    config = DraftConfig.from_board_config(board.config)
    return SettingsResponse(
        execute_config={
            "timeout": config.execute_config.timeout,
            "preferred_executor": config.execute_config.preferred_executor,
            "executor_model": config.execute_config.executor_model,
        },
        board_id=board.id,
    )


# ==================== Planner Config Endpoints ====================


@router.get("/planner", response_model=PlannerConfigResponse)
async def get_planner_config(
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get current planner configuration from board config (DB)."""
    board = await _resolve_board(db, board_id)
    config = DraftConfig.from_board_config(board.config)
    planner = config.planner_config

    return PlannerConfigResponse(
        model=planner.model,
        agent_path=planner.agent_path,
        timeout=planner.timeout,
        preferred_executor=config.execute_config.preferred_executor,
    )


@router.put("/planner", response_model=PlannerConfigResponse)
async def update_planner_config(
    data: PlannerConfigUpdate,
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Update planner model and agent_path in board config (DB)."""
    board = await _resolve_board(db, board_id)

    update_dict: dict[str, Any] = {}
    if data.model is not None:
        update_dict["model"] = data.model
        # When setting cli/<executor>, auto-sync agent_path to the executor name
        if data.model.startswith("cli/") and data.agent_path is None:
            update_dict["agent_path"] = data.model.removeprefix("cli/")
    if data.agent_path is not None:
        update_dict["agent_path"] = data.agent_path

    if update_dict:
        existing = board.config or {}
        board.config = deep_merge_dicts(existing, {"planner_config": update_dict})
        await db.commit()
        await db.refresh(board)

    config = DraftConfig.from_board_config(board.config)
    planner = config.planner_config

    return PlannerConfigResponse(
        model=planner.model,
        agent_path=planner.agent_path,
        timeout=planner.timeout,
        preferred_executor=config.execute_config.preferred_executor,
    )


@router.get("/planner/check", response_model=PlannerHealthResponse)
async def check_planner_health(
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Test if the configured planner can work.

    For CLI models (cli/claude): checks if the CLI binary is available.
    For API models: makes a minimal test call to verify credentials.
    """
    import shutil

    board = await _resolve_board(db, board_id)
    config = DraftConfig.from_board_config(board.config)
    planner = config.planner_config
    model = planner.model

    # CLI mode: check if the agent binary exists
    if model.startswith("cli/"):
        agent_path = planner.get_agent_path()
        found = shutil.which(agent_path)
        if found:
            logger.info(f"Planner CLI health check passed: {agent_path} -> {found}")
            return PlannerHealthResponse(status="online", model=model)
        else:
            return PlannerHealthResponse(
                status="offline",
                model=model,
                error=f"CLI not found: {agent_path}. Install it or add it to PATH.",
            )

    # API mode: make a minimal LLM call
    from app.services.llm_service import LLMService

    try:
        llm = LLMService(planner)
        llm.call_completion(
            messages=[{"role": "user", "content": 'Reply with exactly: {"ok":true}'}],
            max_tokens=20,
            timeout=15,
            json_mode=True,
        )
        logger.info(f"Planner API health check passed: model={model}")
        return PlannerHealthResponse(status="online", model=model)
    except Exception as e:
        logger.warning(f"Planner health check failed: {e}")
        return PlannerHealthResponse(status="offline", model=model, error=str(e))
