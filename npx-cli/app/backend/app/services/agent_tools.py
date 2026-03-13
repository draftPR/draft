"""LangChain tools for UDAR agent.

These tools wrap existing Draft services to make them accessible
to the LangGraph agent. All tools are designed to be deterministic and
minimize LLM calls where possible.
"""

import json
from pathlib import Path

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.ticket import Ticket
from app.services.context_gatherer import ContextGatherer


@tool
async def analyze_codebase(repo_root: str) -> str:
    """Analyze repository structure and gather codebase context.

    This is a DETERMINISTIC tool (0 LLM calls). It uses the existing
    ContextGatherer to scan the repository and return metadata about:
    - Project type (python, node, mixed, etc.)
    - File tree with line counts
    - TODO comments
    - README excerpt

    Args:
        repo_root: Absolute path to repository root

    Returns:
        JSON string with codebase context:
        {
            "project_type": "python",
            "file_count": 150,
            "total_lines": 12500,
            "todo_count": 23,
            "has_readme": true,
            "readme_excerpt": "...",
            "file_tree_sample": ["backend/app/main.py", ...]
        }
    """
    try:
        gatherer = ContextGatherer(max_files=1000)
        context = gatherer.gather(
            repo_root=Path(repo_root),
            include_readme_excerpt=True,
        )

        # Convert to JSON-serializable format
        result = {
            "project_type": context.project_type,
            "file_count": len(context.file_tree),
            "total_lines": sum(f.line_count for f in context.file_tree),
            "todo_count": context.todo_count,
            "has_readme": bool(context.readme_excerpt),
            "readme_excerpt": context.readme_excerpt[:500]
            if context.readme_excerpt
            else None,
            "file_tree_sample": [
                f.path for f in context.file_tree[:50]
            ],  # Cap at 50 files
            "stats": {
                "files_scanned": context.stats.files_scanned,
                "bytes_read": context.stats.bytes_read,
                "excluded_count": context.stats.skipped_excluded,
            },
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "project_type": "unknown",
                "file_count": 0,
            }
        )


@tool
async def search_tickets(
    db: AsyncSession,
    goal_id: str,
    query: str | None = None,
    state: str | None = None,
) -> str:
    """Search existing tickets for a goal.

    This is a DETERMINISTIC tool (0 LLM calls). It queries the database
    to find tickets matching the criteria. Useful for avoiding duplicate
    ticket generation.

    Args:
        db: Database session
        goal_id: Goal ID to search within
        query: Optional text to search in title/description
        state: Optional state filter (e.g., "done", "planned")

    Returns:
        JSON string with ticket list:
        {
            "total": 5,
            "tickets": [
                {
                    "id": "abc-123",
                    "title": "Add authentication",
                    "state": "done",
                    "priority": 90,
                    "blocked_by_ticket_id": null
                },
                ...
            ]
        }
    """
    try:
        # Build query
        stmt = select(Ticket).where(Ticket.goal_id == goal_id)

        if state:
            stmt = stmt.where(Ticket.state == state)

        if query:
            # Simple text search in title and description
            search_term = f"%{query.lower()}%"
            stmt = stmt.where(
                (Ticket.title.ilike(search_term))
                | (Ticket.description.ilike(search_term))
            )

        # Execute query
        result = await db.execute(stmt)
        tickets = result.scalars().all()

        # Convert to JSON-serializable format
        tickets_data = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description[:200]
                if t.description
                else None,  # Cap at 200 chars
                "state": t.state,
                "priority": t.priority,
                "blocked_by_ticket_id": t.blocked_by_ticket_id,
            }
            for t in tickets
        ]

        return json.dumps(
            {
                "total": len(tickets_data),
                "tickets": tickets_data,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "total": 0,
                "tickets": [],
            }
        )


@tool
async def get_goal_context(db: AsyncSession, goal_id: str) -> str:
    """Get goal details and statistics.

    This is a DETERMINISTIC tool (0 LLM calls). It retrieves the goal
    and counts existing tickets by state.

    Args:
        db: Database session
        goal_id: Goal ID to retrieve

    Returns:
        JSON string with goal context:
        {
            "id": "goal-123",
            "title": "Add authentication system",
            "description": "Implement OAuth2...",
            "status": "active",
            "ticket_counts": {
                "proposed": 2,
                "planned": 3,
                "executing": 1,
                "done": 5,
                "total": 11
            }
        }
    """
    try:
        # Get goal
        goal = await db.get(Goal, goal_id)
        if not goal:
            return json.dumps(
                {
                    "error": f"Goal {goal_id} not found",
                    "id": goal_id,
                }
            )

        # Count tickets by state
        stmt = select(Ticket).where(Ticket.goal_id == goal_id)
        result = await db.execute(stmt)
        tickets = result.scalars().all()

        ticket_counts = {}
        for ticket in tickets:
            state = ticket.state
            ticket_counts[state] = ticket_counts.get(state, 0) + 1

        # Build result
        result_data = {
            "id": goal.id,
            "title": goal.title,
            "description": goal.description[:500]
            if goal.description
            else None,  # Cap at 500 chars
            "created_at": goal.created_at.isoformat() if goal.created_at else None,
            "ticket_counts": {
                **ticket_counts,
                "total": len(tickets),
            },
        }

        return json.dumps(result_data, indent=2)

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "id": goal_id,
            }
        )


@tool
async def analyze_ticket_changes(
    db: AsyncSession,
    ticket_id: str,
) -> str:
    """Analyze what changed in a completed ticket (deterministic, 0 LLM calls).

    This tool parses git diffs and evidence to understand changes WITHOUT
    calling an LLM. It extracts file counts, line changes, and verification
    status using deterministic text parsing.

    Args:
        db: Database session
        ticket_id: Ticket ID to analyze

    Returns:
        JSON string with change analysis:
        {
            "ticket_id": "abc-123",
            "ticket_title": "Add authentication",
            "state": "done",
            "files_changed": ["backend/app/auth.py", "backend/app/models.py"],
            "file_count": 2,
            "lines_added": 150,
            "lines_deleted": 20,
            "verification_passed": true,
            "has_revision": true
        }
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.ticket import Ticket

        # Get ticket with revision
        stmt = (
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(selectinload(Ticket.revisions))
        )
        result = await db.execute(stmt)
        ticket = result.scalar_one_or_none()

        if not ticket:
            return json.dumps(
                {
                    "error": f"Ticket {ticket_id} not found",
                    "ticket_id": ticket_id,
                }
            )

        # Get latest revision
        revisions = sorted(ticket.revisions, key=lambda r: r.number, reverse=True)
        latest_revision = revisions[0] if revisions else None

        if not latest_revision:
            return json.dumps(
                {
                    "ticket_id": ticket_id,
                    "ticket_title": ticket.title,
                    "state": ticket.state,
                    "files_changed": [],
                    "file_count": 0,
                    "lines_added": 0,
                    "lines_deleted": 0,
                    "verification_passed": False,
                    "has_revision": False,
                }
            )

        # Load diff stat from evidence (deterministic)
        files_changed = []
        lines_added = 0
        lines_deleted = 0

        if latest_revision.diff_stat_evidence_id:
            from app.models.evidence import Evidence

            evidence = await db.get(Evidence, latest_revision.diff_stat_evidence_id)
            diff_stat_content = None
            if evidence and evidence.stdout_path:
                try:
                    from pathlib import Path

                    diff_stat_content = Path(evidence.stdout_path).read_text()
                except Exception:
                    pass

            if diff_stat_content:
                # Parse diff stat format: "file.py | 10 +++++-----"
                for line in diff_stat_content.split("\n"):
                    if "|" in line:
                        file_part = line.split("|")[0].strip()
                        if file_part:
                            files_changed.append(file_part)

                        plus_count = line.count("+")
                        minus_count = line.count("-")
                        lines_added += plus_count
                        lines_deleted += minus_count

        # Check verification status
        verification_passed = latest_revision.status == "approved"

        result_data = {
            "ticket_id": ticket_id,
            "ticket_title": ticket.title,
            "state": ticket.state,
            "files_changed": files_changed[:20],  # Cap at 20 for prompt size
            "file_count": len(files_changed),
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "verification_passed": verification_passed,
            "has_revision": True,
        }

        return json.dumps(result_data, indent=2)

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "ticket_id": ticket_id,
            }
        )


# Export tools for easy import
__all__ = [
    "analyze_codebase",
    "search_tickets",
    "get_goal_context",
    "analyze_ticket_changes",
]
