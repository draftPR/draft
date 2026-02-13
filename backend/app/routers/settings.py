"""Router for global project settings (smartkanban.yaml)."""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from pydantic import BaseModel
from pathlib import Path
import yaml

from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

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
    execute_config: Dict[str, Any]
    config_path: str


@router.get("", response_model=SettingsResponse)
async def get_global_settings():
    """Get global project settings from smartkanban.yaml.

    Returns:
        Current settings from smartkanban.yaml
    """
    try:
        # Look for smartkanban.yaml in parent directory (project root)
        config_path = Path.cwd().parent / "smartkanban.yaml"

        # If not found, try current directory (when running from project root)
        if not config_path.exists():
            config_path = Path.cwd() / "smartkanban.yaml"

        if not config_path.exists():
            raise HTTPException(status_code=404, detail="smartkanban.yaml not found")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        execute_config = config.get("execute_config", {})

        return SettingsResponse(
            execute_config=execute_config,
            config_path=str(config_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {str(e)}")


@router.put("", response_model=SettingsResponse)
async def update_global_settings(data: SettingsUpdate):
    """Update global project settings in smartkanban.yaml.

    Args:
        data: Settings to update (partial update supported)

    Returns:
        Updated settings
    """
    try:
        # Look for smartkanban.yaml in parent directory (project root)
        config_path = Path.cwd().parent / "smartkanban.yaml"

        # If not found, try current directory (when running from project root)
        if not config_path.exists():
            config_path = Path.cwd() / "smartkanban.yaml"

        if not config_path.exists():
            raise HTTPException(status_code=404, detail="smartkanban.yaml not found")

        # Read current config
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Update execute_config fields if provided
        if data.execute_config:
            if "execute_config" not in config:
                config["execute_config"] = {}

            if data.execute_config.timeout is not None:
                config["execute_config"]["timeout"] = data.execute_config.timeout

            if data.execute_config.preferred_executor is not None:
                config["execute_config"]["preferred_executor"] = data.execute_config.preferred_executor

            if data.execute_config.executor_model is not None:
                config["execute_config"]["executor_model"] = data.execute_config.executor_model

        # Write back to file
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return SettingsResponse(
            execute_config=config.get("execute_config", {}),
            config_path=str(config_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")
