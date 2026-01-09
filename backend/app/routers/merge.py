"""API router for merge operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.schemas.merge import MergeRequest, MergeResponse, MergeStatusResponse
from app.services.merge_service import MergeService, MergeStrategy

router = APIRouter(prefix="/tickets", tags=["merge"])


@router.post(
    "/{ticket_id}/merge",
    response_model=MergeResponse,
    summary="Merge a ticket's changes into the default branch",
    responses={
        200: {"description": "Merge completed (check success field)"},
        404: {"description": "Ticket not found"},
        409: {"description": "Merge conflict or validation error"},
        422: {"description": "Invalid request"},
    },
)
async def merge_ticket(
    ticket_id: str,
    data: MergeRequest,
    db: AsyncSession = Depends(get_db),
) -> MergeResponse:
    """
    Merge a ticket's worktree branch into the default branch.

    Prerequisites:
    - Ticket must be in 'done' state
    - Ticket must have an approved revision
    - Ticket must have an active worktree

    The merge will:
    1. Verify the worktree has no uncommitted changes
    2. Checkout the default branch in the main repo
    3. Pull latest changes (optional, based on config)
    4. Merge or rebase the worktree branch
    5. Optionally delete the worktree and cleanup artifacts

    If the merge fails due to conflicts, the merge is aborted and the
    worktree is left intact for manual resolution.
    """
    service = MergeService(db)

    try:
        # Convert schema enum to service enum
        strategy = MergeStrategy.MERGE if data.strategy.value == "merge" else MergeStrategy.REBASE

        result = await service.merge_ticket(
            ticket_id=ticket_id,
            strategy=strategy,
            delete_worktree=data.delete_worktree,
            cleanup_artifacts=data.cleanup_artifacts,
        )

        return MergeResponse(
            success=result.success,
            message=result.message,
            exit_code=result.exit_code,
            evidence_id=result.evidence_ids.get("meta_id") if result.evidence_ids else None,
            pull_warning=result.pull_warning,
        )

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/{ticket_id}/merge-status",
    response_model=MergeStatusResponse,
    summary="Get merge status for a ticket",
)
async def get_merge_status(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> MergeStatusResponse:
    """
    Get the merge status for a ticket.

    Returns whether the ticket can be merged, whether it has already been
    merged, and information about the workspace and last merge attempt.
    """
    service = MergeService(db)

    try:
        status_info = await service.get_merge_status(ticket_id)
        return MergeStatusResponse(**status_info)
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

