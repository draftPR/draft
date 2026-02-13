"""API router for Repository endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.repo import (
    DiscoverReposRequest,
    DiscoverReposResponse,
    DiscoveredRepoResponse,
    RepoCreate,
    RepoListResponse,
    RepoResponse,
    RepoUpdate,
    ValidateRepoRequest,
    ValidateRepoResponse,
)
from app.services.repo_discovery_service import RepoDiscoveryService

router = APIRouter(prefix="/repos", tags=["repos"])


# ============================================================================
# Repo CRUD endpoints
# ============================================================================


@router.post(
    "",
    response_model=RepoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new repository",
)
async def create_repo(
    data: RepoCreate,
    db: AsyncSession = Depends(get_db),
) -> RepoResponse:
    """
    Register a new git repository in the global registry.

    **Validation:**
    - Path must exist and be a directory
    - Path must be a valid git repository
    - Path must not already be registered

    **Metadata:**
    - Repository name derived from path if not provided
    - Git metadata (default branch, remote URL) auto-detected
    """
    service = RepoDiscoveryService(db)
    try:
        repo = await service.register_repo(
            path=data.path,
            display_name=data.display_name,
            setup_script=data.setup_script,
            cleanup_script=data.cleanup_script,
            dev_server_script=data.dev_server_script,
        )
        return RepoResponse.model_validate(repo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "",
    response_model=RepoListResponse,
    summary="List all registered repositories",
)
async def list_repos(
    db: AsyncSession = Depends(get_db),
) -> RepoListResponse:
    """Get all registered repositories, ordered by creation date (newest first)."""
    service = RepoDiscoveryService(db)
    repos = await service.get_all_repos()
    return RepoListResponse(
        repos=[RepoResponse.model_validate(r) for r in repos],
        total=len(repos),
    )


@router.get(
    "/{repo_id}",
    response_model=RepoResponse,
    summary="Get a repository by ID",
)
async def get_repo(
    repo_id: str,
    db: AsyncSession = Depends(get_db),
) -> RepoResponse:
    """Get a repository by its ID."""
    service = RepoDiscoveryService(db)
    repo = await service.get_repo_by_id(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo not found: {repo_id}")
    return RepoResponse.model_validate(repo)


@router.patch(
    "/{repo_id}",
    response_model=RepoResponse,
    summary="Update a repository",
)
async def update_repo(
    repo_id: str,
    data: RepoUpdate,
    db: AsyncSession = Depends(get_db),
) -> RepoResponse:
    """
    Update a repository's configuration.

    **Updatable fields:**
    - display_name - User-friendly name
    - setup_script - Optional setup script
    - cleanup_script - Optional cleanup script
    - dev_server_script - Optional dev server script

    **Note:** Path and git metadata are read-only.
    """
    service = RepoDiscoveryService(db)
    try:
        repo = await service.update_repo(
            repo_id=repo_id,
            display_name=data.display_name,
            setup_script=data.setup_script,
            cleanup_script=data.cleanup_script,
            dev_server_script=data.dev_server_script,
        )
        return RepoResponse.model_validate(repo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository",
)
async def delete_repo(
    repo_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a repository from the global registry.

    **Warning:** This will cascade delete all BoardRepo associations.
    Boards using this repo will no longer have it available.
    """
    service = RepoDiscoveryService(db)
    try:
        await service.delete_repo(repo_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Discovery endpoints
# ============================================================================


@router.post(
    "/discover",
    response_model=DiscoverReposResponse,
    summary="Discover git repositories",
)
async def discover_repos(
    request: DiscoverReposRequest,
    db: AsyncSession = Depends(get_db),
) -> DiscoverReposResponse:
    """
    Scan directories for git repositories.

    **How it works:**
    1. Walks directory tree up to `max_depth` levels
    2. Excludes common non-repo directories (node_modules, venv, etc.)
    3. Detects .git directories
    4. Extracts git metadata (branch, remote)
    5. Returns list of discovered repos (not yet registered)

    **Example:**
    ```json
    {
      "search_paths": ["~/code", "~/projects"],
      "max_depth": 3,
      "exclude_patterns": ["archive", "old"]
    }
    ```

    **Next steps:**
    - Review discovered repos
    - Use POST /repos to register desired repos
    """
    service = RepoDiscoveryService(db)

    exclude_set = set(request.exclude_patterns) if request.exclude_patterns else None

    discovered = await service.discover_repos(
        search_paths=request.search_paths,
        max_depth=request.max_depth,
        exclude_patterns=exclude_set,
    )

    return DiscoverReposResponse(
        discovered=[
            DiscoveredRepoResponse(
                path=r.path,
                name=r.name,
                display_name=r.display_name,
                default_branch=r.default_branch,
                remote_url=r.remote_url,
                is_valid=r.is_valid,
                error_message=r.error_message,
            )
            for r in discovered
        ],
        total=len(discovered),
    )


@router.post(
    "/validate",
    response_model=ValidateRepoResponse,
    summary="Validate a repository path",
)
async def validate_repo(
    request: ValidateRepoRequest,
    db: AsyncSession = Depends(get_db),
) -> ValidateRepoResponse:
    """
    Validate that a path is a valid git repository.

    **Checks:**
    - Path exists
    - Path is a directory
    - Path contains a .git directory
    - Git repository is accessible

    **Returns:**
    - is_valid: Whether path is a valid repo
    - path: Normalized absolute path
    - metadata: Git metadata if valid
    - error_message: Error description if invalid
    """
    service = RepoDiscoveryService(db)
    validation = await service.validate_repo_path(request.path)

    metadata_response = None
    if validation.metadata:
        metadata_response = DiscoveredRepoResponse(
            path=validation.metadata.path,
            name=validation.metadata.name,
            display_name=validation.metadata.display_name,
            default_branch=validation.metadata.default_branch,
            remote_url=validation.metadata.remote_url,
            is_valid=validation.metadata.is_valid,
            error_message=validation.metadata.error_message,
        )

    return ValidateRepoResponse(
        is_valid=validation.is_valid,
        path=validation.path,
        error_message=validation.error_message,
        metadata=metadata_response,
    )
