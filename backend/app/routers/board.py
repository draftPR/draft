"""API router for Board endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.board import (
    BoardConfigResponse,
    BoardConfigUpdate,
    BoardCreate,
    BoardListResponse,
    BoardResponse,
    BoardUpdate,
)
from app.schemas.planner import AnalyzeCodebaseRequest, AnalyzeCodebaseResponse
from app.schemas.repo import (
    BoardRepoCreate,
    BoardRepoListResponse,
    BoardRepoResponse,
    BoardRepoUpdate,
)
from app.schemas.ticket import BoardResponse as KanbanBoardResponse
from app.services.board_repo_service import BoardRepoService
from app.services.board_service import BoardService
from app.services.config_service import ConfigService
from app.services.ticket_generation_service import TicketGenerationService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/boards", tags=["boards"])


# ============================================================================
# Board CRUD endpoints
# ============================================================================

@router.post(
    "",
    response_model=BoardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new board",
)
async def create_board(
    data: BoardCreate,
    db: AsyncSession = Depends(get_db),
) -> BoardResponse:
    """Create a new board with a repository root.

    **Important:** The repo_root must be an absolute path to an existing
    git repository. This becomes the authoritative path for all file
    operations on this board.
    """
    service = BoardService(db)
    try:
        board = await service.create_board(data)
        return BoardResponse.model_validate(board)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "",
    response_model=BoardListResponse,
    summary="List all boards",
)
async def list_boards(
    db: AsyncSession = Depends(get_db),
) -> BoardListResponse:
    """Get all boards."""
    service = BoardService(db)
    boards = await service.get_boards()
    return BoardListResponse(
        boards=[BoardResponse.model_validate(b) for b in boards],
        total=len(boards),
    )


@router.get(
    "/{board_id}",
    response_model=BoardResponse,
    summary="Get a board by ID",
)
async def get_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> BoardResponse:
    """Get a board by its ID."""
    service = BoardService(db)
    try:
        board = await service.get_board_by_id(board_id)
        return BoardResponse.model_validate(board)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch(
    "/{board_id}",
    response_model=BoardResponse,
    summary="Update a board",
)
async def update_board(
    board_id: str,
    data: BoardUpdate,
    db: AsyncSession = Depends(get_db),
) -> BoardResponse:
    """Update a board's name, description, or default branch."""
    service = BoardService(db)
    try:
        board = await service.update_board(board_id, data)
        return BoardResponse.model_validate(board)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{board_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a board",
)
async def delete_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a board and all its associated goals, tickets, jobs, workspaces."""
    service = BoardService(db)
    try:
        await service.delete_board(board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Board Configuration endpoints
# ============================================================================

@router.get(
    "/{board_id}/config",
    response_model=BoardConfigResponse,
    summary="Get board configuration",
)
async def get_board_config(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> BoardConfigResponse:
    """
    Get the board-level configuration overrides.

    Returns the raw config JSON stored in the board, which overrides
    settings from smartkanban.yaml in the repository.

    Configuration priority (highest to lowest):
    1. Board config (this endpoint)
    2. YAML config (smartkanban.yaml)
    3. Defaults
    """
    service = BoardService(db)
    try:
        board = await service.get_board_by_id(board_id)
        return BoardConfigResponse(
            board_id=board.id,
            config=board.config,
            has_overrides=board.config is not None and len(board.config) > 0,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/{board_id}/config",
    response_model=BoardConfigResponse,
    summary="Update board configuration",
)
async def update_board_config(
    board_id: str,
    data: BoardConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> BoardConfigResponse:
    """
    Update board-level configuration overrides.

    This performs a **partial deep merge** - only provided fields are updated,
    nested objects are merged (not replaced).

    Example:
        Existing config: {"execute_config": {"timeout": 600, "executor_model": "opus"}}
        Update: {"execute_config": {"executor_model": "auto"}}
        Result: {"execute_config": {"timeout": 600, "executor_model": "auto"}}

    To clear a specific field, set it to null in the request.
    To clear all overrides, use DELETE /boards/{board_id}/config.
    """
    service = BoardService(db)
    try:
        board = await service.get_board_by_id(board_id)

        # Convert Pydantic model to dict, excluding None values
        update_dict = data.model_dump(exclude_none=True)

        if not update_dict:
            # No updates provided
            return BoardConfigResponse(
                board_id=board.id,
                config=board.config,
                has_overrides=board.config is not None and len(board.config) > 0,
            )

        # Deep merge with existing config
        from app.services.config_service import deep_merge_dicts
        existing_config = board.config or {}
        merged_config = deep_merge_dicts(existing_config, update_dict)

        # Update board
        from app.schemas.board import BoardUpdate
        update_data = BoardUpdate(config=merged_config)
        board = await service.update_board(board_id, update_data)

        return BoardConfigResponse(
            board_id=board.id,
            config=board.config,
            has_overrides=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{board_id}/config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear board configuration",
)
async def clear_board_config(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Clear all board-level configuration overrides.

    After this, the board will use settings from smartkanban.yaml only.
    """
    service = BoardService(db)
    try:
        from app.schemas.board import BoardUpdate
        await service.update_board(board_id, BoardUpdate(config=None))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{board_id}/config/initialize",
    response_model=BoardConfigResponse,
    summary="Initialize board configuration with defaults",
)
async def initialize_board_config(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> BoardConfigResponse:
    """
    Initialize board configuration with sensible defaults if config is null.

    This is useful for boards created before auto-initialization was implemented.
    If the board already has config, this is a no-op.

    Default config includes:
    - executor_model: "sonnet-4.5" (fast and cost-effective)
    - timeout: 300 (5 minutes)
    """
    service = BoardService(db)
    try:
        board = await service.initialize_board_config(board_id)
        return BoardConfigResponse(
            board_id=board.id,
            config=board.config,
            has_overrides=board.config is not None and len(board.config) > 0,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/config/initialize-all",
    summary="Initialize configuration for all boards with null config",
)
async def initialize_all_board_configs(
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize configuration for all boards that have config=null.

    This is a maintenance endpoint useful for migrating existing boards
    to the new auto-initialization behavior.

    Returns a summary of how many boards were updated.
    """
    service = BoardService(db)
    result = await service.initialize_all_board_configs()
    return result


@router.delete(
    "/{board_id}/tickets",
    summary="Delete all tickets from a board",
)
async def delete_all_tickets(
    board_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete all tickets from a board.

    **WARNING:** This action cannot be undone!

    This will cascade delete all associated:
    - Jobs
    - Revisions (and their review comments/summaries)
    - Ticket events
    - Workspaces
    - Evidence files

    Worktrees are cleaned up asynchronously (best effort).
    """
    # Verify board exists
    board_service = BoardService(db)
    try:
        await board_service.get_board_by_id(board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Delete all tickets for this board
    ticket_service = TicketService(db)
    count = await ticket_service.delete_all_tickets(board_id=board_id)

    return {
        "deleted_count": count,
        "message": f"Deleted {count} ticket(s) from board {board_id}",
    }


@router.get(
    "/{board_id}/board",
    response_model=KanbanBoardResponse,
    summary="Get the kanban board view for a specific board",
)
async def get_board_kanban(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> KanbanBoardResponse:
    """
    Get the kanban board view with all tickets for this board grouped by state.

    Returns tickets organized into columns by state, ordered by priority
    (highest first) within each column.

    Only tickets belonging to this board are included.
    """
    # Verify board exists
    board_service = BoardService(db)
    try:
        await board_service.get_board_by_id(board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Get tickets for this board
    service = TicketService(db)
    columns = await service.get_board(board_id=board_id)

    # Count total tickets (conversion already handled in service)
    total_tickets = sum(len(column.tickets) for column in columns)

    return KanbanBoardResponse(
        columns=columns,
        total_tickets=total_tickets,
    )


# ============================================================================
# Board-scoped operations (use board's repo_root, NOT client-provided paths)
# ============================================================================

@router.post(
    "/{board_id}/analyze-codebase",
    response_model=AnalyzeCodebaseResponse,
    summary="Analyze codebase and generate improvement tickets",
)
async def analyze_codebase(
    board_id: str,
    request: AnalyzeCodebaseRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeCodebaseResponse:
    """
    Analyze the board's repository codebase and generate improvement tickets.

    **Security:**
    - Repository path is taken from the board's repo_root, NOT from client request
    - Sensitive files (.env, keys, secrets) are automatically excluded
    - Only metadata and small excerpts are sent to the LLM

    **Caching:**
    - Results are cached for 10 minutes to avoid expensive repeated LLM calls
    - `cache_hit: true` in response indicates cached result

    **Focus Areas (optional):**
    - `security`: Look for security issues
    - `performance`: Look for performance problems
    - `tests`: Look for missing tests
    - `docs`: Look for documentation gaps

    **Goal attachment:**
    - If `goal_id` is provided, tickets are created in the database
    - If `goal_id` is omitted, returns preview only (no DB write)
    - **Goal must belong to this board** (board_id check enforced)

    **Tickets include priority buckets:**
    - P0 (90): Critical - security, data loss
    - P1 (70): High - important features, performance
    - P2 (50): Medium - improvements
    - P3 (30): Low - cleanup, docs
    """
    # Get repo_root from board (authoritative source)
    board_service = BoardService(db)
    try:
        repo_root = await board_service.get_repo_root(board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not repo_root.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Board's repo_root does not exist: {repo_root}",
        )

    # If goal_id provided, verify it belongs to this board
    if request.goal_id:
        from sqlalchemy import select

        from app.models import Goal

        result = await db.execute(
            select(Goal).where(Goal.id == request.goal_id)
        )
        goal = result.scalar_one_or_none()
        if not goal:
            raise HTTPException(status_code=404, detail=f"Goal not found: {request.goal_id}")
        if goal.board_id and goal.board_id != board_id:
            raise HTTPException(
                status_code=403,
                detail=f"Goal {request.goal_id} belongs to board {goal.board_id}, not {board_id}",
            )

    service = TicketGenerationService(db)
    try:
        return await service.analyze_codebase(
            repo_root=repo_root,
            goal_id=request.goal_id,
            focus_areas=request.focus_areas,
            include_readme=request.include_readme,
            board_id=board_id,  # Pass board_id for context/caching
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Board-Repo Association endpoints
# ============================================================================


@router.get(
    "/{board_id}/repos",
    response_model=BoardRepoListResponse,
    summary="Get repos for a board",
)
async def get_board_repos(
    board_id: str,
    db: AsyncSession = Depends(get_db),
) -> BoardRepoListResponse:
    """
    Get all repositories associated with a board.

    Returns repos ordered by:
    1. Primary repos first
    2. Then by creation date (oldest first)
    """
    # Verify board exists
    board_service = BoardService(db)
    try:
        await board_service.get_board_by_id(board_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Get board repos
    board_repo_service = BoardRepoService(db)
    board_repos = await board_repo_service.get_board_repos(board_id)

    return BoardRepoListResponse(
        board_id=board_id,
        repos=[BoardRepoResponse.model_validate(br) for br in board_repos],
        total=len(board_repos),
    )


@router.post(
    "/{board_id}/repos",
    response_model=BoardRepoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a repo to a board",
)
async def add_repo_to_board(
    board_id: str,
    data: BoardRepoCreate,
    db: AsyncSession = Depends(get_db),
) -> BoardRepoResponse:
    """
    Associate a repository with a board.

    **Notes:**
    - Repo must already be registered (use POST /repos first)
    - If is_primary=true, this becomes the primary repo (others are unset)
    - Custom scripts override the repo's default scripts for this board
    """
    board_repo_service = BoardRepoService(db)
    try:
        board_repo = await board_repo_service.add_repo_to_board(
            board_id=board_id,
            repo_id=data.repo_id,
            is_primary=data.is_primary,
            custom_setup_script=data.custom_setup_script,
            custom_cleanup_script=data.custom_cleanup_script,
        )
        return BoardRepoResponse.model_validate(board_repo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/{board_id}/repos/{repo_id}",
    response_model=BoardRepoResponse,
    summary="Update board-repo association",
)
async def update_board_repo(
    board_id: str,
    repo_id: str,
    data: BoardRepoUpdate,
    db: AsyncSession = Depends(get_db),
) -> BoardRepoResponse:
    """
    Update a board-repo association.

    **Common use case:** Set a repo as primary via `is_primary: true`
    """
    board_repo_service = BoardRepoService(db)
    try:
        board_repo = await board_repo_service.update_board_repo(
            board_id=board_id,
            repo_id=repo_id,
            is_primary=data.is_primary,
            custom_setup_script=data.custom_setup_script,
            custom_cleanup_script=data.custom_cleanup_script,
        )
        return BoardRepoResponse.model_validate(board_repo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{board_id}/repos/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove repo from board",
)
async def remove_repo_from_board(
    board_id: str,
    repo_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a repository from a board.

    **Warning:** This does not delete the repo itself, only the association.
    The repo remains in the global registry.
    """
    board_repo_service = BoardRepoService(db)
    try:
        await board_repo_service.remove_repo_from_board(board_id, repo_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Legacy kanban board view (kept for backwards compatibility)
# ============================================================================

# Create a separate router for the legacy /board endpoint
legacy_router = APIRouter(prefix="/board", tags=["board"])


@legacy_router.get(
    "",
    response_model=KanbanBoardResponse,
    summary="Get the kanban board view",
)
async def get_kanban_board(
    db: AsyncSession = Depends(get_db),
) -> KanbanBoardResponse:
    """
    Get the kanban board view with all tickets grouped by state.

    Returns tickets organized into columns by state, ordered by priority
    (highest first) within each column.

    **Note:** This is a legacy endpoint. For multi-board support, use
    GET /boards/{board_id}/tickets instead.
    """
    service = TicketService(db)
    columns = await service.get_board()

    # Count total tickets (conversion already handled in service)
    total_tickets = sum(len(column.tickets) for column in columns)

    return KanbanBoardResponse(
        columns=columns,
        total_tickets=total_tickets,
    )


@legacy_router.post(
    "/analyze-codebase",
    response_model=AnalyzeCodebaseResponse,
    summary="[DEPRECATED] Analyze codebase - use /boards/{board_id}/analyze-codebase",
    deprecated=True,
)
async def analyze_codebase_legacy(
    request: AnalyzeCodebaseRequest,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeCodebaseResponse:
    """
    **DEPRECATED:** Use POST /boards/{board_id}/analyze-codebase instead.

    This endpoint uses the repo_root from smartkanban.yaml config.
    The board-scoped endpoint is preferred for multi-board setups.
    """
    # Get repo root from config - legacy path
    config_service = ConfigService()
    config = config_service.load_config()
    repo_root = Path(config.project.repo_root).resolve()

    if not repo_root.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Configured repo_root does not exist: {repo_root}",
        )

    service = TicketGenerationService(db)
    try:
        return await service.analyze_codebase(
            repo_root=repo_root,
            goal_id=request.goal_id,
            focus_areas=request.focus_areas,
            include_readme=request.include_readme,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
