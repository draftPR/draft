"""API router for merge and conflict resolution operations."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.models.board import Board
from app.models.ticket import Ticket
from app.schemas.merge import (
    AbortResponse,
    ConflictStatusResponse,
    MergeRequest,
    MergeResponse,
    MergeStatusResponse,
    PushResponse,
    PushStatusResponse,
    RebaseResponse,
)
from app.services.merge_service import MergeService, MergeStrategy

router = APIRouter(prefix="/tickets", tags=["merge"])


async def _get_ticket_worktree(ticket_id: str, db: AsyncSession) -> tuple[Ticket, Path]:
    """Get ticket and its active worktree path. Raises HTTP errors."""
    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(selectinload(Ticket.workspace))
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    if not ticket.workspace or not ticket.workspace.is_active:
        raise HTTPException(status_code=404, detail="Ticket has no active worktree")

    worktree_path = Path(ticket.workspace.worktree_path)
    if not worktree_path.exists():
        raise HTTPException(status_code=404, detail="Worktree directory not found")

    return ticket, worktree_path


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
    # Load board config for merge settings
    board_config = None
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket_obj = ticket_result.scalar_one_or_none()
    if ticket_obj and ticket_obj.board_id:
        board_result = await db.execute(
            select(Board).where(Board.id == ticket_obj.board_id)
        )
        board_obj = board_result.scalar_one_or_none()
        if board_obj:
            board_config = board_obj.config

    service = MergeService(db, board_config=board_config)

    try:
        # Convert schema enum to service enum
        strategy = (
            MergeStrategy.MERGE
            if data.strategy.value == "merge"
            else MergeStrategy.REBASE
        )

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
            evidence_id=result.evidence_ids.get("meta_id")
            if result.evidence_ids
            else None,
            pull_warning=result.pull_warning,
        )

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


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
        ) from e


# ===================== Conflict Resolution Endpoints =====================


@router.get(
    "/{ticket_id}/conflict-status",
    response_model=ConflictStatusResponse,
    summary="Check if a ticket's worktree has conflicts",
)
async def get_conflict_status(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConflictStatusResponse:
    """Check for conflicts in the ticket's worktree.

    Returns conflict state, affected files, and whether continue/abort is possible.
    Also returns branch divergence info for merge planning.
    """
    from app.services.git_ops import detect_conflict_state, get_divergence_info

    ticket, worktree_path = await _get_ticket_worktree(ticket_id, db)

    state = await asyncio.to_thread(detect_conflict_state, worktree_path)

    # Get divergence info
    from app.services.workspace_service import WorkspaceService

    repo_path = WorkspaceService.get_repo_path()
    branch_name = ticket.workspace.branch_name
    divergence = await asyncio.to_thread(get_divergence_info, repo_path, branch_name)

    if state is None:
        return ConflictStatusResponse(
            has_conflict=False,
            operation=None,
            conflicted_files=[],
            can_continue=False,
            can_abort=False,
            divergence=divergence,
        )

    return ConflictStatusResponse(
        has_conflict=True,
        operation=state.operation,
        conflicted_files=state.conflicted_files,
        can_continue=state.can_continue,
        can_abort=state.can_abort,
        divergence=divergence,
    )


@router.post(
    "/{ticket_id}/rebase",
    response_model=RebaseResponse,
    summary="Rebase a ticket's branch onto the target branch",
)
async def rebase_ticket(
    ticket_id: str,
    onto_branch: str = "main",
    db: AsyncSession = Depends(get_db),
) -> RebaseResponse:
    """Rebase the ticket's worktree branch onto the target branch.

    Use this when the base branch has moved forward (divergence detected).
    If conflicts arise, use continue-rebase or abort-conflict.
    """
    from app.services.git_ops import rebase_branch

    _, worktree_path = await _get_ticket_worktree(ticket_id, db)

    result = await asyncio.to_thread(rebase_branch, worktree_path, onto_branch)

    return RebaseResponse(
        success=result.success,
        message=result.message,
        has_conflicts=result.has_conflicts,
        conflicted_files=result.conflicted_files,
    )


@router.post(
    "/{ticket_id}/continue-rebase",
    response_model=RebaseResponse,
    summary="Continue a paused rebase after resolving conflicts",
)
async def continue_rebase_endpoint(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> RebaseResponse:
    """Continue a rebase that paused due to conflicts.

    Call this after the AI agent (or user) has resolved conflicts in the worktree.
    """
    from app.services.git_ops import continue_rebase

    _, worktree_path = await _get_ticket_worktree(ticket_id, db)

    result = await asyncio.to_thread(continue_rebase, worktree_path)

    return RebaseResponse(
        success=result.success,
        message=result.message,
        has_conflicts=result.has_conflicts,
        conflicted_files=result.conflicted_files,
    )


@router.post(
    "/{ticket_id}/abort-conflict",
    response_model=AbortResponse,
    summary="Abort the current conflict operation",
)
async def abort_conflict_endpoint(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> AbortResponse:
    """Abort the current conflict operation (rebase, merge, cherry-pick, etc.).

    Returns the worktree to its pre-operation state.
    """
    from app.services.git_ops import abort_operation

    _, worktree_path = await _get_ticket_worktree(ticket_id, db)

    success = await asyncio.to_thread(abort_operation, worktree_path)

    return AbortResponse(
        success=success,
        message="Operation aborted successfully"
        if success
        else "Failed to abort operation",
    )


# ===================== Push Endpoints =====================


@router.get(
    "/{ticket_id}/push-status",
    response_model=PushStatusResponse,
    summary="Check if a ticket's branch needs to be pushed",
)
async def get_push_status_endpoint(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> PushStatusResponse:
    """Check if the ticket's branch is ahead/behind the remote tracking branch."""
    from app.services.git_ops import get_push_status

    ticket, worktree_path = await _get_ticket_worktree(ticket_id, db)
    branch_name = ticket.workspace.branch_name

    result = await asyncio.to_thread(get_push_status, worktree_path, branch_name)
    return PushStatusResponse(**result)


@router.post(
    "/{ticket_id}/push",
    response_model=PushResponse,
    summary="Push a ticket's branch to remote",
)
async def push_ticket_branch(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> PushResponse:
    """Push the ticket's worktree branch to the remote origin."""
    from app.services.git_ops import push_branch

    ticket, worktree_path = await _get_ticket_worktree(ticket_id, db)
    branch_name = ticket.workspace.branch_name

    result = await asyncio.to_thread(push_branch, worktree_path, branch_name)
    return PushResponse(success=result.success, message=result.message)


@router.post(
    "/{ticket_id}/force-push",
    response_model=PushResponse,
    summary="Force-push a ticket's branch to remote (with lease)",
)
async def force_push_ticket_branch(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> PushResponse:
    """Force-push the ticket's branch using --force-with-lease for safety.

    Use after rebase when the remote branch already exists.
    """
    from app.services.git_ops import force_push_branch

    ticket, worktree_path = await _get_ticket_worktree(ticket_id, db)
    branch_name = ticket.workspace.branch_name

    result = await asyncio.to_thread(force_push_branch, worktree_path, branch_name)
    return PushResponse(success=result.success, message=result.message)
