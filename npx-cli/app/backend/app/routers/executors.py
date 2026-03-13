"""Router for executor management and listing."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.executors.registry import ExecutorRegistry
from app.models.board import Board
from app.services.config_service import DraftConfig, deep_merge_dicts

router = APIRouter(prefix="/executors", tags=["executors"])


@router.get("/available", response_model=list[dict[str, Any]])
async def list_available_executors():
    """List all available executors (both installed and not installed).

    Returns:
        List of executor metadata with availability status
    """
    try:
        # Get all registered executors via public API
        all_executors = []

        for metadata in ExecutorRegistry.list_all():
            adapter = ExecutorRegistry.get(metadata.name)
            is_available = await adapter.is_available()

            executor_dict = {
                "name": metadata.name,
                "display_name": metadata.display_name,
                "version": metadata.version,
                "capabilities": [cap.value for cap in metadata.capabilities],
                "config_schema": metadata.config_schema,
                "documentation_url": metadata.documentation_url,
                "author": metadata.author,
                "license": metadata.license,
                "available": is_available,
            }

            all_executors.append(executor_dict)

        return all_executors

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list executors: {str(e)}"
        )


@router.get("/{executor_name}/metadata", response_model=dict[str, Any])
async def get_executor_metadata(executor_name: str):
    """Get metadata for a specific executor.

    Args:
        executor_name: Name of the executor

    Returns:
        Executor metadata
    """
    try:
        adapter = ExecutorRegistry.get(executor_name)
        metadata = adapter.get_metadata()
        is_available = await adapter.is_available()

        return {
            "name": metadata.name,
            "display_name": metadata.display_name,
            "version": metadata.version,
            "capabilities": [cap.value for cap in metadata.capabilities],
            "config_schema": metadata.config_schema,
            "documentation_url": metadata.documentation_url,
            "author": metadata.author,
            "license": metadata.license,
            "available": is_available,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


@router.get("/{executor_name}/models", response_model=list[dict[str, str]])
async def list_executor_models(executor_name: str):
    """List available models for a given executor type.

    Returns a list of model options that can be used with this executor.
    """
    # Model options per executor type
    models_by_executor: dict[str, list[dict[str, str]]] = {
        "claude": [
            {
                "id": "auto",
                "name": "Auto (recommended)",
                "description": "Automatically select the best model",
            },
            {
                "id": "claude-sonnet-4-20250514",
                "name": "Claude Sonnet 4",
                "description": "Fast and capable",
            },
            {
                "id": "claude-opus-4-20250514",
                "name": "Claude Opus 4",
                "description": "Most capable model",
            },
        ],
        "cursor-agent": [
            {
                "id": "auto",
                "name": "Auto (recommended)",
                "description": "Automatically select the best model",
            },
        ],
        "cursor": [
            {
                "id": "auto",
                "name": "Auto (recommended)",
                "description": "Uses Cursor IDE model selection",
            },
        ],
    }

    models = models_by_executor.get(executor_name)
    if models is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown executor: {executor_name}",
        )
    return models


@router.get("/{executor_name}/available")
async def check_executor_available(executor_name: str):
    """Check if a specific executor is available (installed).

    Args:
        executor_name: Name of the executor

    Returns:
        Dict with availability status
    """
    try:
        adapter = ExecutorRegistry.get(executor_name)
        is_available = await adapter.is_available()

        return {"name": executor_name, "available": is_available}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check availability: {str(e)}"
        )


@router.get("/{executor_name}/setup")
async def get_executor_setup(executor_name: str):
    """Get setup instructions and availability diagnostics for an executor.

    Returns detailed information about whether the executor is installed,
    what issues exist, and how to set it up.

    Args:
        executor_name: Name of the executor

    Returns:
        Dict with availability diagnostics and setup instructions
    """
    try:
        adapter = ExecutorRegistry.get(executor_name)
        diagnostics = await adapter.check_availability()
        metadata = adapter.get_metadata()

        return {
            "name": metadata.name,
            "display_name": metadata.display_name,
            **diagnostics,
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check setup: {str(e)}")


async def _resolve_board_for_executors(db: AsyncSession, board_id: str | None) -> Board:
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


@router.get("/profiles", response_model=list[dict[str, Any]])
async def list_executor_profiles(
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """List all configured executor profiles from board config (DB).

    Returns:
        List of executor profile configurations
    """
    board = await _resolve_board_for_executors(db, board_id)
    config = DraftConfig.from_board_config(board.config)
    profiles = config.executor_profiles

    return [
        {
            "name": profile.name,
            "executor_type": profile.executor_type,
            "timeout": profile.timeout,
            "extra_flags": profile.extra_flags,
            "model": profile.model,
            "env": profile.env,
        }
        for profile in profiles.values()
    ]


@router.get("/profiles/{profile_name}", response_model=dict[str, Any])
async def get_executor_profile(
    profile_name: str,
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific executor profile by name.

    Args:
        profile_name: Name of the profile

    Returns:
        Executor profile configuration
    """
    board = await _resolve_board_for_executors(db, board_id)
    config = DraftConfig.from_board_config(board.config)
    profile = config.executor_profiles.get(profile_name)

    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Executor profile '{profile_name}' not found",
        )

    return {
        "name": profile.name,
        "executor_type": profile.executor_type,
        "timeout": profile.timeout,
        "extra_flags": profile.extra_flags,
        "model": profile.model,
        "env": profile.env,
    }


@router.put("/profiles", response_model=list[dict[str, Any]])
async def save_executor_profiles(
    profiles: list[dict[str, Any]],
    board_id: str | None = Query(
        None, description="Board ID (uses first board if omitted)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Save executor profiles to board config (DB).

    Replaces all profiles with the provided list.
    """
    board = await _resolve_board_for_executors(db, board_id)

    # Build profiles dict for storage
    profiles_dict: dict[str, Any] = {}
    for p in profiles:
        name = p.get("name", "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {}
        if p.get("executor_type"):
            entry["executor_type"] = p["executor_type"]
        if p.get("timeout"):
            entry["timeout"] = int(p["timeout"])
        if p.get("extra_flags"):
            entry["extra_flags"] = p["extra_flags"]
        if p.get("model"):
            entry["model"] = p["model"]
        if p.get("env"):
            entry["env"] = p["env"]
        profiles_dict[name] = entry

    existing = board.config or {}
    board.config = deep_merge_dicts(existing, {"executor_profiles": profiles_dict})
    await db.commit()
    await db.refresh(board)

    config = DraftConfig.from_board_config(board.config)
    return [
        {
            "name": prof.name,
            "executor_type": prof.executor_type,
            "timeout": prof.timeout,
            "extra_flags": prof.extra_flags,
            "model": prof.model,
            "env": prof.env,
        }
        for prof in config.executor_profiles.values()
    ]
