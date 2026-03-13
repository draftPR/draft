"""Pull Request router for GitHub integration."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ConfigurationError
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.workspace import Workspace
from app.services.git_host import get_git_host_provider
from app.state_machine import ActorType, EventType, TicketState, validate_transition

router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])


class CreatePRRequest(BaseModel):
    """Request to create a GitHub Pull Request."""

    ticket_id: str
    title: str | None = None
    body: str | None = None
    base_branch: str = "main"


class PRStatusResponse(BaseModel):
    """Response with PR status information."""

    pr_number: int
    pr_url: str
    pr_state: str
    pr_created_at: datetime | None
    pr_merged_at: datetime | None
    pr_head_branch: str | None
    pr_base_branch: str | None


class AddPRCommentRequest(BaseModel):
    """Request to add a comment to a PR."""

    body: str


class PRCommentResponse(BaseModel):
    """A single PR comment."""

    author: str
    body: str
    created_at: str


class MergePRRequest(BaseModel):
    """Request to merge a PR."""

    strategy: str = "squash"  # squash, merge, rebase


@router.post("", response_model=PRStatusResponse)
async def create_pull_request(
    request: CreatePRRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a GitHub Pull Request for a ticket.

    This will:
    1. Get the ticket and its workspace
    2. Push the workspace branch to remote
    3. Create a PR using GitHub CLI
    4. Update ticket with PR information
    5. Transition ticket to REVIEW state
    """
    # Get ticket
    result = await db.execute(select(Ticket).where(Ticket.id == request.ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=404, detail=f"Ticket {request.ticket_id} not found"
        )

    # Check if PR already exists
    if ticket.pr_number:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket already has PR #{ticket.pr_number}: {ticket.pr_url}",
        )

    # Get workspace
    result = await db.execute(
        select(Workspace).where(Workspace.ticket_id == request.ticket_id)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=400,
            detail=f"Ticket {request.ticket_id} has no workspace. Cannot create PR.",
        )

    if not workspace.worktree_path:
        raise HTTPException(
            status_code=400,
            detail=f"Workspace for ticket {request.ticket_id} has no worktree path.",
        )

    repo_path = Path(workspace.worktree_path)

    if not repo_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Workspace path does not exist: {workspace.worktree_path}",
        )

    # Determine branch name
    head_branch = workspace.branch_name or f"ticket-{ticket.id[:8]}"

    # Use provided title/body or generate defaults
    pr_title = request.title or ticket.title
    pr_body = request.body or (
        f"Implements: {ticket.title}\n\n"
        f"{ticket.description or ''}\n\n"
        f"Ticket ID: {ticket.id}"
    )

    # Get git host provider (auto-detects GitHub vs GitLab)
    git_host = get_git_host_provider(repo_path)

    try:
        # Check if authenticated
        await git_host.ensure_authenticated()

        # Create PR/MR
        pr = await git_host.create_pr(
            repo_path=repo_path,
            title=pr_title,
            body=pr_body,
            head_branch=head_branch,
            base_branch=request.base_branch,
        )

        # Update ticket with PR information
        ticket.pr_number = pr.number
        ticket.pr_url = pr.url
        ticket.pr_state = pr.state
        ticket.pr_created_at = datetime.now()
        ticket.pr_head_branch = pr.head_branch
        ticket.pr_base_branch = pr.base_branch

        await db.commit()
        await db.refresh(ticket)

        return PRStatusResponse(
            pr_number=ticket.pr_number,
            pr_url=ticket.pr_url,
            pr_state=ticket.pr_state,
            pr_created_at=ticket.pr_created_at,
            pr_merged_at=ticket.pr_merged_at,
            pr_head_branch=ticket.pr_head_branch,
            pr_base_branch=ticket.pr_base_branch,
        )

    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to create PR: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/{ticket_id}", response_model=PRStatusResponse)
async def get_pr_status(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the PR status for a ticket."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

    if not ticket.pr_number:
        raise HTTPException(
            status_code=404, detail=f"Ticket {ticket_id} has no associated PR"
        )

    return PRStatusResponse(
        pr_number=ticket.pr_number,
        pr_url=ticket.pr_url,
        pr_state=ticket.pr_state,
        pr_created_at=ticket.pr_created_at,
        pr_merged_at=ticket.pr_merged_at,
        pr_head_branch=ticket.pr_head_branch,
        pr_base_branch=ticket.pr_base_branch,
    )


@router.post("/{ticket_id}/refresh", response_model=PRStatusResponse)
async def refresh_pr_status(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually refresh the PR status from GitHub.

    This will fetch the latest PR state from GitHub and update the ticket.
    """
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

    if not ticket.pr_number:
        raise HTTPException(
            status_code=404, detail=f"Ticket {ticket_id} has no associated PR"
        )

    # Get workspace for repo path
    result = await db.execute(select(Workspace).where(Workspace.ticket_id == ticket_id))
    workspace = result.scalar_one_or_none()

    if not workspace or not workspace.worktree_path:
        raise HTTPException(
            status_code=400,
            detail="Cannot refresh PR status: workspace not found or no worktree path",
        )

    repo_path = Path(workspace.worktree_path)

    try:
        git_host = get_git_host_provider(repo_path)
        pr_details = await git_host.get_pr_details(repo_path, ticket.pr_number)

        # Update ticket
        old_state = ticket.pr_state
        ticket.pr_state = pr_details["state"]

        if pr_details.get("merged") and not ticket.pr_merged_at:
            ticket.pr_merged_at = datetime.now()

        # Auto-transition ticket if PR was merged
        if pr_details.get("merged") and old_state != "MERGED":
            ticket.pr_state = "MERGED"
            current_state = TicketState(ticket.state)
            if validate_transition(current_state, TicketState.DONE):
                ticket.state = TicketState.DONE.value
                event = TicketEvent(
                    ticket_id=ticket.id,
                    event_type=EventType.TRANSITIONED.value,
                    from_state=current_state.value,
                    to_state=TicketState.DONE.value,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id="pr_refresh",
                    reason="PR merged on remote",
                )
                db.add(event)

        await db.commit()
        await db.refresh(ticket)

        return PRStatusResponse(
            pr_number=ticket.pr_number,
            pr_url=ticket.pr_url,
            pr_state=ticket.pr_state,
            pr_created_at=ticket.pr_created_at,
            pr_merged_at=ticket.pr_merged_at,
            pr_head_branch=ticket.pr_head_branch,
            pr_base_branch=ticket.pr_base_branch,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh PR status: {str(e)}"
        )


# ===================== PR Comment Endpoints =====================


async def _get_ticket_with_pr(ticket_id: str, db: AsyncSession) -> tuple:
    """Get ticket with PR info and workspace repo path."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    if not ticket.pr_number:
        raise HTTPException(status_code=400, detail="Ticket has no associated PR")

    result = await db.execute(select(Workspace).where(Workspace.ticket_id == ticket_id))
    workspace = result.scalar_one_or_none()
    if not workspace or not workspace.worktree_path:
        raise HTTPException(status_code=400, detail="No workspace found for ticket")

    repo_path = Path(workspace.worktree_path)
    return ticket, repo_path


@router.post("/{ticket_id}/comments", response_model=dict)
async def add_pr_comment(
    ticket_id: str,
    request: AddPRCommentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a ticket's PR."""
    ticket, repo_path = await _get_ticket_with_pr(ticket_id, db)
    git_host = get_git_host_provider(repo_path)

    try:
        result = await git_host.add_pr_comment(
            repo_path, ticket.pr_number, request.body
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add comment: {str(e)}")


@router.get("/{ticket_id}/comments", response_model=list[PRCommentResponse])
async def list_pr_comments(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all comments on a ticket's PR."""
    ticket, repo_path = await _get_ticket_with_pr(ticket_id, db)
    git_host = get_git_host_provider(repo_path)

    try:
        comments = await git_host.list_pr_comments(repo_path, ticket.pr_number)
        return [
            PRCommentResponse(
                author=c.get("author", {}).get("login", "unknown"),
                body=c.get("body", ""),
                created_at=c.get("createdAt", ""),
            )
            for c in comments
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list comments: {str(e)}"
        )


@router.post("/{ticket_id}/merge", response_model=dict)
async def merge_pr_endpoint(
    ticket_id: str,
    request: MergePRRequest,
    db: AsyncSession = Depends(get_db),
):
    """Merge a ticket's PR on GitHub with the given strategy."""
    ticket, repo_path = await _get_ticket_with_pr(ticket_id, db)
    git_host = get_git_host_provider(repo_path)

    try:
        result = await git_host.merge_pr(repo_path, ticket.pr_number, request.strategy)

        # Update ticket state on successful merge
        ticket.pr_state = "MERGED"
        ticket.pr_merged_at = datetime.now()
        current_state = TicketState(ticket.state)
        if validate_transition(current_state, TicketState.DONE):
            ticket.state = TicketState.DONE.value
            event = TicketEvent(
                ticket_id=ticket.id,
                event_type=EventType.TRANSITIONED.value,
                from_state=current_state.value,
                to_state=TicketState.DONE.value,
                actor_type=ActorType.SYSTEM.value,
                actor_id="pr_merge",
                reason="PR merged",
            )
            db.add(event)
        await db.commit()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to merge PR: {str(e)}")
