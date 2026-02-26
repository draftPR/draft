"""Router for global project settings (smartkanban.yaml)."""

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    config_path: str


# --- Planner config models ---


class PlannerConfigResponse(BaseModel):
    """Planner configuration response."""

    model: str
    agent_path: str
    timeout: int


class PlannerConfigUpdate(BaseModel):
    """Planner configuration update."""

    model: str | None = None
    agent_path: str | None = None


class PlannerHealthResponse(BaseModel):
    """Planner health check response."""

    status: str  # "online" | "offline"
    model: str
    error: str | None = None


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

        with open(config_path) as f:
            config = yaml.safe_load(f)

        execute_config = config.get("execute_config", {})

        return SettingsResponse(
            execute_config=execute_config, config_path=str(config_path)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read settings: {str(e)}"
        )


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
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Update execute_config fields if provided
        if data.execute_config:
            if "execute_config" not in config:
                config["execute_config"] = {}

            if data.execute_config.timeout is not None:
                config["execute_config"]["timeout"] = data.execute_config.timeout

            if data.execute_config.preferred_executor is not None:
                config["execute_config"]["preferred_executor"] = (
                    data.execute_config.preferred_executor
                )

            if data.execute_config.executor_model is not None:
                config["execute_config"]["executor_model"] = (
                    data.execute_config.executor_model
                )

        # Write back to file
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return SettingsResponse(
            execute_config=config.get("execute_config", {}),
            config_path=str(config_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update settings: {str(e)}"
        )


# ==================== Planner Config Endpoints ====================


def _find_config_path() -> Path:
    """Find the smartkanban.yaml config file path."""
    config_path = Path.cwd().parent / "smartkanban.yaml"
    if not config_path.exists():
        config_path = Path.cwd() / "smartkanban.yaml"
    return config_path


@router.get("/planner", response_model=PlannerConfigResponse)
async def get_planner_config():
    """Get current planner configuration from smartkanban.yaml."""
    try:
        from app.services.config_service import ConfigService

        config_service = ConfigService()
        planner = config_service.get_planner_config()

        return PlannerConfigResponse(
            model=planner.model,
            agent_path=planner.agent_path,
            timeout=planner.timeout,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to read planner config: {str(e)}"
        )


@router.put("/planner", response_model=PlannerConfigResponse)
async def update_planner_config(data: PlannerConfigUpdate):
    """Update planner model and agent_path in smartkanban.yaml."""
    try:
        config_path = _find_config_path()
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="smartkanban.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        if "planner_config" not in config:
            config["planner_config"] = {}

        if data.model is not None:
            config["planner_config"]["model"] = data.model

        if data.agent_path is not None:
            config["planner_config"]["agent_path"] = data.agent_path

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Re-read to return current state
        from app.services.config_service import ConfigService

        config_service = ConfigService()
        planner = config_service.get_planner_config()

        return PlannerConfigResponse(
            model=planner.model,
            agent_path=planner.agent_path,
            timeout=planner.timeout,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update planner config: {str(e)}"
        )


@router.get("/planner/check", response_model=PlannerHealthResponse)
async def check_planner_health():
    """Test if the configured planner can work.

    For CLI models (cli/claude): checks if the CLI binary is available.
    For API models: makes a minimal test call to verify credentials.
    """
    import shutil

    from app.services.config_service import ConfigService

    config_service = ConfigService()
    planner = config_service.get_planner_config()
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
