"""API router for Revision and Review endpoints."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.models.job import Job, JobKind, JobStatus
from app.models.review_comment import AuthorType
from app.models.review_summary import ReviewDecision
from app.models.revision import RevisionStatus
from app.schemas.common import PaginatedResponse
from app.schemas.review import (
    FeedbackBundle,
    ReviewCommentCreate,
    ReviewCommentListResponse,
    ReviewCommentResponse,
    ReviewSubmit,
    ReviewSummaryResponse,
)
from app.schemas.revision import (
    DiffFile,
    DiffPatchResponse,
    DiffSummaryResponse,
    RevisionDetailResponse,
    RevisionDiffResponse,
    RevisionListResponse,
    RevisionResponse,
    RevisionTimelineResponse,
    TimelineEvent,
)
from app.services.review_service import ReviewService
from app.services.revision_service import RevisionService
from app.services.ticket_service import TicketService
from app.state_machine import ActorType as TicketActorType
from app.state_machine import TicketState

router = APIRouter(tags=["revisions"])


# ==================== Revision Endpoints ====================


@router.get(
    "/tickets/{ticket_id}/revisions",
    response_model=RevisionListResponse,
    summary="Get all revisions for a ticket",
)
async def get_ticket_revisions(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
) -> RevisionListResponse:
    """Get all revisions for a ticket, ordered by revision number descending."""
    service = RevisionService(db)
    try:
        revisions = await service.get_revisions_for_ticket(ticket_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    revision_responses = [
        RevisionResponse(
            id=r.id,
            ticket_id=r.ticket_id,
            job_id=r.job_id,
            number=r.number,
            status=RevisionStatus(r.status),
            diff_stat_evidence_id=r.diff_stat_evidence_id,
            diff_patch_evidence_id=r.diff_patch_evidence_id,
            created_at=r.created_at,
            unresolved_comment_count=r.unresolved_comment_count,
        )
        for r in revisions
    ]

    return RevisionListResponse(
        revisions=revision_responses,
        total=len(revision_responses),
    )


@router.get(
    "/revisions/{revision_id}",
    response_model=RevisionDetailResponse,
    summary="Get a revision by ID",
)
async def get_revision(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> RevisionDetailResponse:
    """Get detailed information about a revision including diff content."""
    service = RevisionService(db)
    try:
        revision = await service.get_revision_by_id(revision_id)
        diff_stat, diff_patch = await service.get_revision_diff(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return RevisionDetailResponse(
        id=revision.id,
        ticket_id=revision.ticket_id,
        job_id=revision.job_id,
        number=revision.number,
        status=RevisionStatus(revision.status),
        diff_stat_evidence_id=revision.diff_stat_evidence_id,
        diff_patch_evidence_id=revision.diff_patch_evidence_id,
        created_at=revision.created_at,
        unresolved_comment_count=revision.unresolved_comment_count,
        diff_stat=diff_stat,
        diff_patch=diff_patch,
    )


@router.get(
    "/revisions/{revision_id}/diff",
    response_model=RevisionDiffResponse,
    summary="Get the diff content for a revision",
)
async def get_revision_diff(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> RevisionDiffResponse:
    """Get the diff content for a revision with parsed file information."""
    service = RevisionService(db)
    try:
        diff_stat, diff_patch = await service.get_revision_diff(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    # Parse diff stat to extract file information
    files = _parse_diff_stat(diff_stat) if diff_stat else []

    return RevisionDiffResponse(
        revision_id=revision_id,
        diff_stat=diff_stat,
        diff_patch=diff_patch,
        files=files,
    )


@router.get(
    "/revisions/{revision_id}/diff/summary",
    response_model=DiffSummaryResponse,
    summary="Get lightweight diff summary (stat + file list)",
)
async def get_revision_diff_summary(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> DiffSummaryResponse:
    """Get the lightweight diff summary for initial UI load.

    This returns only the diff stat and file list - no heavy patch content.
    Use this for the file tree view. Only fetch /diff/patch when user actually
    opens the diff viewer.
    """
    service = RevisionService(db)
    try:
        diff_stat = await service.get_revision_diff_summary(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    # Parse diff stat to extract file information
    files = _parse_diff_stat(diff_stat) if diff_stat else []

    return DiffSummaryResponse(
        revision_id=revision_id,
        diff_stat=diff_stat,
        files=files,
    )


@router.get(
    "/revisions/{revision_id}/diff/patch",
    response_model=DiffPatchResponse,
    summary="Get heavyweight diff patch content",
)
async def get_revision_diff_patch(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> DiffPatchResponse:
    """Get the full diff patch content.

    This is a heavyweight endpoint - only call when user actually opens
    the diff viewer and wants to see the code changes.
    """
    service = RevisionService(db)
    try:
        diff_patch = await service.get_revision_diff_patch(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return DiffPatchResponse(
        revision_id=revision_id,
        diff_patch=diff_patch,
    )


def _parse_diff_stat(diff_stat: str) -> list[DiffFile]:
    """Parse git diff --stat output to extract file information.

    Example input:
        backend/app/models/ticket.py | 10 +++++-----
        backend/app/services/new.py  | 50 +++++++++++++++++++++++++++++++++++
        2 files changed, 55 insertions(+), 5 deletions(-)
    """
    files = []
    # Match lines like: path/to/file | 10 +++++-----
    pattern = r"^\s*(.+?)\s+\|\s+(\d+)\s+(\+*)(\-*)\s*$"

    for line in diff_stat.split("\n"):
        match = re.match(pattern, line)
        if match:
            path = match.group(1).strip()
            additions = len(match.group(3))
            deletions = len(match.group(4))

            # Determine status
            if "=>" in path:  # renamed
                status = "renamed"
                # Extract old and new paths from "old => new"
                parts = path.split("=>")
                if len(parts) == 2:
                    old_path = parts[0].strip().strip("{").strip()
                    new_path = parts[1].strip().strip("}").strip()
                    files.append(
                        DiffFile(
                            path=new_path,
                            old_path=old_path,
                            additions=additions,
                            deletions=deletions,
                            status=status,
                        )
                    )
                    continue
            elif additions > 0 and deletions == 0:
                # Could be new file, but git diff --stat doesn't clearly indicate
                status = "modified"  # Default to modified
            elif deletions > 0 and additions == 0:
                status = "modified"
            else:
                status = "modified"

            files.append(
                DiffFile(
                    path=path,
                    additions=additions,
                    deletions=deletions,
                    status=status,
                )
            )

    return files


# ==================== Review Comment Endpoints ====================


@router.post(
    "/revisions/{revision_id}/comments",
    response_model=ReviewCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an inline comment to a revision",
)
async def add_comment(
    revision_id: str,
    data: ReviewCommentCreate,
    db: AsyncSession = Depends(get_db),
) -> ReviewCommentResponse:
    """Add an inline comment on a specific line in the revision diff.

    Returns 409 Conflict if the revision is superseded.
    """
    service = ReviewService(db)
    try:
        comment = await service.add_comment(
            revision_id=revision_id,
            file_path=data.file_path,
            line_number=data.line_number,
            body=data.body,
            author_type=AuthorType(data.author_type.value),
            hunk_header=data.hunk_header,
            line_content=data.line_content,
        )
        await db.commit()
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=e.message)

    return ReviewCommentResponse(
        id=comment.id,
        revision_id=comment.revision_id,
        file_path=comment.file_path,
        line_number=comment.line_number,
        anchor=comment.anchor,
        body=comment.body,
        author_type=comment.author_type_enum,
        resolved=comment.resolved,
        created_at=comment.created_at,
        line_content=comment.line_content,
    )


@router.get(
    "/revisions/{revision_id}/comments",
    summary="Get all comments for a revision",
)
async def get_revision_comments(
    revision_id: str,
    include_resolved: bool = True,
    page: int | None = Query(
        None,
        ge=1,
        description="Page number (1-based). Omit for all results.",
    ),
    limit: int | None = Query(
        None,
        ge=1,
        le=200,
        description="Items per page. Omit for all results.",
    ),
    db: AsyncSession = Depends(get_db),
) -> ReviewCommentListResponse | PaginatedResponse[ReviewCommentResponse]:
    """Get all comments for a revision.

    **Pagination (optional):**
    - If `page` and `limit` are provided, returns paginated response.
    - If omitted, returns all comments (backward compatible).
    """
    service = ReviewService(db)
    try:
        comments = await service.get_comments_for_revision(
            revision_id, include_resolved=include_resolved
        )
        unresolved_count = await service.get_unresolved_count(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    comment_responses = [
        ReviewCommentResponse(
            id=c.id,
            revision_id=c.revision_id,
            file_path=c.file_path,
            line_number=c.line_number,
            anchor=c.anchor,
            body=c.body,
            author_type=c.author_type_enum,
            resolved=c.resolved,
            created_at=c.created_at,
        )
        for c in comments
    ]

    # If pagination params are provided, return paginated response
    if page is not None and limit is not None:
        total = len(comment_responses)
        offset = (page - 1) * limit
        page_items = comment_responses[offset : offset + limit]
        return PaginatedResponse[ReviewCommentResponse](
            items=page_items,
            total=total,
            page=page,
            limit=limit,
        )

    # Backward compatible: return all
    return ReviewCommentListResponse(
        comments=comment_responses,
        total=len(comment_responses),
        unresolved_count=unresolved_count,
    )


@router.post(
    "/comments/{comment_id}/resolve",
    response_model=ReviewCommentResponse,
    summary="Resolve a comment",
)
async def resolve_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReviewCommentResponse:
    """Mark a comment as resolved."""
    service = ReviewService(db)
    try:
        comment = await service.resolve_comment(comment_id)
        await db.commit()
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return ReviewCommentResponse(
        id=comment.id,
        revision_id=comment.revision_id,
        file_path=comment.file_path,
        line_number=comment.line_number,
        anchor=comment.anchor,
        body=comment.body,
        author_type=comment.author_type_enum,
        resolved=comment.resolved,
        created_at=comment.created_at,
        line_content=comment.line_content,
    )


@router.post(
    "/comments/{comment_id}/unresolve",
    response_model=ReviewCommentResponse,
    summary="Unresolve a comment",
)
async def unresolve_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReviewCommentResponse:
    """Mark a comment as unresolved."""
    service = ReviewService(db)
    try:
        comment = await service.unresolve_comment(comment_id)
        await db.commit()
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)

    return ReviewCommentResponse(
        id=comment.id,
        revision_id=comment.revision_id,
        file_path=comment.file_path,
        line_number=comment.line_number,
        anchor=comment.anchor,
        body=comment.body,
        author_type=comment.author_type_enum,
        resolved=comment.resolved,
        created_at=comment.created_at,
        line_content=comment.line_content,
    )


# ==================== Review Decision Endpoints ====================


@router.post(
    "/revisions/{revision_id}/review",
    response_model=ReviewSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review decision for a revision",
)
async def submit_review(
    revision_id: str,
    data: ReviewSubmit,
    db: AsyncSession = Depends(get_db),
) -> ReviewSummaryResponse:
    """Submit a review decision (approve or request changes) for a revision.

    If approved:
    - Ticket transitions to 'done'

    If changes_requested with auto_run_fix=true:
    - Creates a new execute job to address feedback
    - Agent will receive feedback bundle in its prompt

    Returns 409 Conflict if the revision is superseded.
    """
    review_service = ReviewService(db)
    revision_service = RevisionService(db)

    # Initialize merge status (will be populated if merge is attempted)
    merge_attempted = False
    merge_success = None
    merge_message = None

    try:
        # Get revision to find ticket_id
        revision = await revision_service.get_revision_by_id(revision_id)

        # Submit the review
        review_summary = await review_service.submit_review(
            revision_id=revision_id,
            decision=ReviewDecision(data.decision.value),
            summary=data.summary,
        )

        # Handle post-review actions
        ticket_service = TicketService(db)

        if data.decision.value == ReviewDecision.APPROVED.value:
            # Get ticket to check current state
            ticket = await ticket_service.get_ticket_by_id(revision.ticket_id)

            # Detect target branch from board config or git
            target_branch = "main"  # fallback
            board = None
            if ticket.board_id:
                from sqlalchemy import select as sql_select_board

                from app.models.board import Board

                board_result = await db.execute(
                    sql_select_board(Board).where(Board.id == ticket.board_id)
                )
                board = board_result.scalar_one_or_none()
                if board and board.default_branch:
                    target_branch = board.default_branch

            # CRITICAL: Do NOT transition to DONE yet - it triggers worktree cleanup!
            # We need the worktree to exist for PR creation or merge.
            # Transition happens AFTER merge/PR creation.

            if data.create_pr:
                # Create a GitHub PR instead of merging directly
                from pathlib import Path

                from sqlalchemy import select as sql_select

                from app.models.workspace import Workspace
                from app.services.git_host import get_git_host_provider

                # Get workspace to find worktree path and branch
                workspace_result = await db.execute(
                    sql_select(Workspace).where(
                        Workspace.ticket_id == revision.ticket_id
                    )
                )
                workspace = workspace_result.scalar_one_or_none()

                if workspace and workspace.worktree_path:
                    try:
                        repo_path = Path(workspace.worktree_path)
                        git_host = get_git_host_provider(repo_path)
                        await git_host.ensure_authenticated()

                        head_branch = workspace.branch_name or f"ticket-{ticket.id[:8]}"

                        pr = await git_host.create_pr(
                            repo_path=repo_path,
                            title=ticket.title,
                            body=(
                                f"Implements: {ticket.title}\n\n"
                                f"{ticket.description or ''}\n\n"
                                f"Ticket ID: {ticket.id}"
                            ),
                            head_branch=head_branch,
                            base_branch=target_branch,
                        )

                        # Update ticket with PR information
                        from datetime import UTC, datetime

                        ticket.pr_number = pr.number
                        ticket.pr_url = pr.url
                        ticket.pr_state = pr.state
                        ticket.pr_created_at = datetime.now(UTC)
                        ticket.pr_head_branch = pr.head_branch
                        ticket.pr_base_branch = pr.base_branch

                        logger.info(
                            f"Created PR #{pr.number} for ticket {ticket.id}: {pr.url}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to create PR for ticket {ticket.id}: {e}"
                        )
                else:
                    logger.warning(
                        f"No workspace found for ticket {ticket.id}, skipping PR creation"
                    )

                # Transition to DONE after PR creation (worktree will be kept for PR)
                if ticket.state != TicketState.DONE.value:
                    await ticket_service.transition_ticket(
                        ticket_id=revision.ticket_id,
                        to_state=TicketState.DONE,
                        actor_type=TicketActorType.HUMAN,
                        reason="Revision approved by reviewer",
                        auto_verify=False,
                        skip_cleanup=True,  # Worktree kept for PR
                    )
            else:
                # Auto-merge using simple git operations (no state coupling)
                from datetime import UTC, datetime
                from pathlib import Path

                from sqlalchemy import select as sql_select

                from app.models.workspace import Workspace
                from app.services.git_merge_simple import (
                    GitMergeError,
                    cleanup_worktree,
                    git_merge_worktree_branch,
                )
                from app.services.workspace_service import WorkspaceService

                # Track merge status to return to frontend
                merge_attempted = True
                merge_success = False
                merge_message = None

                try:
                    # Get workspace info
                    workspace_result = await db.execute(
                        sql_select(Workspace).where(
                            Workspace.ticket_id == revision.ticket_id
                        )
                    )
                    workspace = workspace_result.scalar_one_or_none()

                    if not workspace or not workspace.is_active:
                        merge_message = "No active workspace found for ticket"
                        logger.info(
                            f"Skipping merge for ticket {revision.ticket_id}: {merge_message}"
                        )
                    else:
                        worktree_path = Path(workspace.worktree_path)
                        branch_name = workspace.branch_name

                        # Get repo path
                        workspace_service = WorkspaceService(db)
                        repo_path = workspace_service.get_repo_path()

                        # Ensure worktree exists
                        if not worktree_path.exists():
                            merge_message = f"Worktree does not exist: {worktree_path}"
                            logger.warning(
                                f"Cannot merge ticket {revision.ticket_id}: {merge_message}"
                            )
                        else:
                            # Simple git merge (runs in thread pool to avoid blocking)
                            # Read merge configuration with board-level overrides
                            from app.services.config_service import ConfigService

                            config_service = ConfigService()

                            # Reuse board fetched earlier for target_branch detection
                            board_config = (
                                board.config if board and board.config else None
                            )

                            # Load config with board overrides applied
                            config = config_service.load_config_with_board_overrides(
                                board_config=board_config, use_cache=False
                            )
                            merge_config = config.merge_config

                            import asyncio

                            merge_result = await asyncio.to_thread(
                                git_merge_worktree_branch,
                                repo_path=repo_path,
                                branch_name=branch_name,
                                target_branch=target_branch,
                                delete_branch_after=merge_config.delete_branch_after_merge,
                                push_to_remote=merge_config.push_after_merge,
                                squash=merge_config.squash_merge,
                                check_divergence=merge_config.check_divergence,
                            )

                            merge_success = merge_result.success
                            merge_message = merge_result.message
                            logger.info(
                                f"Merge result for ticket {revision.ticket_id}: {merge_message}"
                            )

                            # Record merge event so merge-status correctly reports is_merged
                            if merge_success:
                                import json as _json

                                from app.models.ticket_event import TicketEvent
                                from app.state_machine import (
                                    TicketState as SM_TicketState,
                                )

                                merge_event = TicketEvent(
                                    ticket_id=revision.ticket_id,
                                    event_type="merge_succeeded",
                                    from_state=SM_TicketState.DONE.value,
                                    to_state=SM_TicketState.DONE.value,
                                    actor_type="system",
                                    actor_id="review_auto_merge",
                                    reason=f"Auto-merged on approval: {merge_message}",
                                    payload_json=_json.dumps(
                                        {
                                            "strategy": "merge",
                                            "worktree_branch": branch_name,
                                            "base_branch": target_branch,
                                            "auto_merge": True,
                                        }
                                    ),
                                )
                                db.add(merge_event)

                            # Cleanup worktree
                            if merge_success:
                                cleanup_success = await asyncio.to_thread(
                                    cleanup_worktree,
                                    repo_path=repo_path,
                                    worktree_path=worktree_path,
                                )
                                if cleanup_success:
                                    # Mark workspace as cleaned up
                                    workspace.cleaned_up_at = datetime.now(UTC)
                                    logger.info(
                                        f"Cleaned up worktree for ticket {revision.ticket_id}"
                                    )

                except GitMergeError as e:
                    merge_message = f"Git merge failed: {str(e)}"
                    logger.error(
                        f"Merge error for ticket {revision.ticket_id}: {merge_message}"
                    )
                except Exception as e:
                    merge_message = f"Unexpected merge error: {str(e)}"
                    logger.error(
                        f"Unexpected error during merge for ticket {revision.ticket_id}: {e}",
                        exc_info=True,
                    )

                # Transition to DONE after merge attempt (even if merge failed - review was approved)
                if ticket.state != TicketState.DONE.value:
                    await ticket_service.transition_ticket(
                        ticket_id=revision.ticket_id,
                        to_state=TicketState.DONE,
                        actor_type=TicketActorType.HUMAN,
                        reason="Revision approved by reviewer",
                        auto_verify=False,
                        skip_cleanup=True,  # Merge path handles cleanup above
                    )
        elif (
            data.decision.value == ReviewDecision.CHANGES_REQUESTED.value
            and data.auto_run_fix
        ):
            # Auto-rerun caps to prevent infinite loops:
            # - Max 2 auto-reruns per revision (per source_revision_id)
            # - Max 5 total revisions per ticket overall
            MAX_AUTO_RERUNS_PER_REVISION = 2
            MAX_REVISIONS_PER_TICKET = 5

            # Check per-revision rerun cap (how many times THIS revision has been addressed)
            from sqlalchemy import select as sql_select

            rerun_result = await db.execute(
                sql_select(Job).where(Job.source_revision_id == revision_id)
            )
            reruns_from_this_revision = len(list(rerun_result.scalars().all()))

            if reruns_from_this_revision >= MAX_AUTO_RERUNS_PER_REVISION:
                raise ValidationError(
                    f"Maximum auto-reruns ({MAX_AUTO_RERUNS_PER_REVISION}) from this revision reached. "
                    "Please manually create an execute job or resolve the feedback differently."
                )

            # Check per-ticket total revisions cap
            revisions_list = await revision_service.get_revisions_for_ticket(
                revision.ticket_id
            )
            if len(revisions_list) >= MAX_REVISIONS_PER_TICKET:
                raise ValidationError(
                    f"Maximum total revisions ({MAX_REVISIONS_PER_TICKET}) for this ticket reached. "
                    "Consider creating a new ticket for remaining work."
                )

            # Transition to executing and create new execute job
            await ticket_service.transition_ticket(
                ticket_id=revision.ticket_id,
                to_state=TicketState.EXECUTING,
                actor_type=TicketActorType.HUMAN,
                reason="Changes requested - triggering agent re-execution",
                auto_verify=False,
            )

            # Create new execute job with source_revision_id for traceability
            from app.services.task_dispatch import enqueue_task

            job = Job(
                ticket_id=revision.ticket_id,
                kind=JobKind.EXECUTE.value,
                status=JobStatus.QUEUED.value,
                source_revision_id=revision_id,  # Track which revision is being addressed
            )
            db.add(job)
            await db.flush()
            await db.refresh(job)

            # Commit BEFORE enqueue_task to release the SQLite write lock.
            # enqueue_task opens a separate sqlite3 connection which would
            # deadlock if this session still holds the write lock.
            await db.commit()

            # Enqueue the execute task (outside write lock)
            task = enqueue_task("execute_ticket", args=[job.id])
            job.celery_task_id = task.id
            await db.commit()

    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return ReviewSummaryResponse(
        id=review_summary.id,
        revision_id=review_summary.revision_id,
        decision=review_summary.decision_enum,
        body=review_summary.body,
        created_at=review_summary.created_at,
        merge_attempted=merge_attempted,
        merge_success=merge_success,
        merge_message=merge_message,
    )


@router.get(
    "/revisions/{revision_id}/feedback-bundle",
    response_model=FeedbackBundle,
    summary="Get the feedback bundle for a revision",
)
async def get_feedback_bundle(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeedbackBundle:
    """Get the structured feedback bundle for a revision.

    This is the feedback that gets injected into the agent prompt
    when creating a new revision after changes are requested.
    """
    service = ReviewService(db)
    try:
        return await service.get_feedback_bundle(revision_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.get(
    "/revisions/{revision_id}/timeline",
    response_model=RevisionTimelineResponse,
    summary="Get the review timeline for a revision",
)
async def get_revision_timeline(
    revision_id: str,
    db: AsyncSession = Depends(get_db),
) -> RevisionTimelineResponse:
    """Get the timeline of events for a revision.

    Shows a chronological feed of:
    - Revision created
    - Comments added
    - Review submitted
    - Jobs queued/completed
    """
    from sqlalchemy import select as sql_select
    from sqlalchemy.orm import selectinload

    from app.models.revision import Revision

    # Get revision with all related data
    result = await db.execute(
        sql_select(Revision)
        .where(Revision.id == revision_id)
        .options(
            selectinload(Revision.comments),
            selectinload(Revision.review_summary),
            selectinload(Revision.job),
        )
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise HTTPException(status_code=404, detail=f"Revision {revision_id} not found")

    events: list[TimelineEvent] = []

    # Event 1: Revision created
    events.append(
        TimelineEvent(
            id=f"rev-{revision.id}",
            event_type="revision_created",
            actor="agent",
            message=f"Revision {revision.number} created by executor",
            created_at=revision.created_at,
            metadata={"revision_number": revision.number, "job_id": revision.job_id},
        )
    )

    # Event 2: Comments added
    for comment in revision.comments:
        events.append(
            TimelineEvent(
                id=f"comment-{comment.id}",
                event_type="comment_added",
                actor=comment.author_type,
                message=f"Comment on {comment.file_path}:{comment.line_number}",
                created_at=comment.created_at,
                metadata={
                    "file_path": comment.file_path,
                    "line_number": comment.line_number,
                    "resolved": comment.resolved,
                },
            )
        )

    # Event 3: Review submitted
    if revision.review_summary:
        events.append(
            TimelineEvent(
                id=f"review-{revision.review_summary.id}",
                event_type="review_submitted",
                actor="human",
                message=f"Review: {revision.review_summary.decision}",
                created_at=revision.review_summary.created_at,
                metadata={"decision": revision.review_summary.decision},
            )
        )

    # Event 4: Follow-up jobs (jobs with source_revision_id = this revision)
    followup_result = await db.execute(
        sql_select(Job).where(Job.source_revision_id == revision_id)
    )
    followup_jobs = list(followup_result.scalars().all())
    for job in followup_jobs:
        events.append(
            TimelineEvent(
                id=f"job-{job.id}",
                event_type="job_queued" if job.status == "queued" else "job_completed",
                actor="system",
                message=f"Auto rerun queued (job {job.id[:8]}...)"
                if job.status == "queued"
                else f"Auto rerun {job.status}",
                created_at=job.created_at,
                metadata={"job_id": job.id, "job_status": job.status},
            )
        )

    # Sort events by created_at
    events.sort(key=lambda e: e.created_at)

    return RevisionTimelineResponse(
        revision_id=revision_id,
        events=events,
    )
