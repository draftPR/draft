"""Pull Request router for GitHub integration."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ConfigurationError
from app.models.ticket import Ticket
from app.models.workspace import Workspace
from app.services.git_host import get_git_host_provider
from app.state_machine import TicketState

router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])


class CreatePRRequest(BaseModel):
    """Request to create a GitHub Pull Request."""

    ticket_id: str
    title: Optional[str] = None
    body: Optional[str] = None
    base_branch: str = "main"


class PRStatusResponse(BaseModel):
    """Response with PR status information."""

    pr_number: int
    pr_url: str
    pr_state: str
    pr_created_at: Optional[datetime]
    pr_merged_at: Optional[datetime]
    pr_head_branch: Optional[str]
    pr_base_branch: Optional[str]


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
    head_branch = workspace.branch or f"ticket-{ticket.id[:8]}"

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
            detail=f"Cannot refresh PR status: workspace not found or no worktree path",
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
            ticket.state = TicketState.DONE.value
            ticket.pr_state = "MERGED"

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
