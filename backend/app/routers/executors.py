"""Router for executor management and listing."""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.executors.registry import ExecutorRegistry
from app.services.config_service import ConfigService

router = APIRouter(prefix="/executors", tags=["executors"])


@router.get("/available", response_model=list[dict[str, Any]])
async def list_available_executors():
    """List all available executors (both installed and not installed).

    Returns:
        List of executor metadata with availability status
    """
    try:
        # Get all registered executors
        all_executors = []

        for _name, adapter_class in ExecutorRegistry._adapters.items():
            adapter = adapter_class()
            metadata = adapter.get_metadata()
            is_available = await adapter.is_available()

            # Convert to dict for JSON serialization
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


@router.get("/profiles", response_model=list[dict[str, Any]])
async def list_executor_profiles():
    """List all configured executor profiles from smartkanban.yaml.

    Returns:
        List of executor profile configurations
    """
    config_service = ConfigService()
    profiles = config_service.get_executor_profiles()

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
async def get_executor_profile(profile_name: str):
    """Get a specific executor profile by name.

    Args:
        profile_name: Name of the profile

    Returns:
        Executor profile configuration
    """
    config_service = ConfigService()
    profile = config_service.get_executor_profile(profile_name)

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
async def save_executor_profiles(profiles: list[dict[str, Any]]):
    """Save executor profiles to smartkanban.yaml.

    Replaces all profiles with the provided list.
    """
    config_service = ConfigService()
    saved = config_service.save_executor_profiles(profiles)

    return [
        {
            "name": p.name,
            "executor_type": p.executor_type,
            "timeout": p.timeout,
            "extra_flags": p.extra_flags,
            "model": p.model,
            "env": p.env,
        }
        for p in saved.values()
    ]
