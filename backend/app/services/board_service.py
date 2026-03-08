"""Service for Board operations and authorization.

CRITICAL: Board is the primary permission boundary.
- All goals, tickets, jobs, workspaces belong to a board
- All filesystem operations use board.repo_root (NEVER global config)
- All mutating endpoints must validate board_id ownership
"""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Board, Goal, Job, Ticket, Workspace
from app.schemas.board import BoardCreate, BoardUpdate


class BoardService:
    """Service for managing boards and enforcing board boundaries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_default_board_config() -> dict:
        """Get full default configuration for new boards.

        Returns a complete SmartKanbanConfig as a dict so that the DB
        is the single source of truth (no YAML needed at runtime).

        Key defaults:
        - executor_model: "sonnet-4.5" (fast and cost-effective)
        - timeout: 300 (5 minutes, reasonable for most tasks)
        """
        from app.services.config_service import SmartKanbanConfig

        config = SmartKanbanConfig()
        full = config.to_dict()
        # Override with our preferred defaults
        full["execute_config"]["executor_model"] = "sonnet-4.5"
        full["execute_config"]["timeout"] = 300
        return full

    async def create_board(
        self, data: BoardCreate, owner_id: str | None = None
    ) -> Board:
        """Create a new board with sensible default configuration.

        CRITICAL: repo_root becomes the authoritative path for all
        filesystem operations on this board.

        The board is initialized with default config to prevent falling back
        to YAML config which may have non-optimal defaults (e.g., "auto" model).

        If template_id is provided, applies template configuration and creates
        starter goals (unless create_starter_goals=False).
        """
        # Validate repo_root exists and is a git repo
        repo_path = Path(data.repo_root).resolve()
        if not repo_path.exists():
            raise ValueError(f"repo_root does not exist: {data.repo_root}")
        if not repo_path.is_dir():
            raise ValueError(f"repo_root is not a directory: {data.repo_root}")
        if not (repo_path / ".git").exists():
            raise ValueError(f"repo_root is not a git repository: {data.repo_root}")

        # Apply template config if template_id provided
        board_config = self.get_default_board_config()
        if data.template_id:
            from app.templates import get_template

            template = get_template(data.template_id)
            if not template:
                raise ValueError(f"Invalid template_id: {data.template_id}")

            # Merge template config with defaults (template takes precedence)
            if template.get("config"):
                from app.services.config_service import deep_merge_dicts

                board_config = deep_merge_dicts(board_config, template["config"])

        board = Board(
            id=str(uuid.uuid4()),
            name=data.name,
            description=data.description,
            repo_root=str(repo_path),  # Store resolved absolute path
            default_branch=data.default_branch,
            config=board_config,
            owner_id=owner_id,
        )
        self.db.add(board)
        await self.db.commit()
        await self.db.refresh(board)

        # Create starter goals if template provided and requested
        if data.template_id and data.create_starter_goals:
            from app.templates import get_template

            template = get_template(data.template_id)
            if template and template.get("starter_goals"):
                for goal_data in template["starter_goals"]:
                    goal = Goal(
                        id=str(uuid.uuid4()),
                        board_id=board.id,
                        title=goal_data["title"],
                        description=goal_data["description"],
                    )
                    self.db.add(goal)

                await self.db.commit()

        return board

    async def get_board_by_id(self, board_id: str) -> Board:
        """Get a board by its ID."""
        result = await self.db.execute(select(Board).where(Board.id == board_id))
        board = result.scalar_one_or_none()
        if not board:
            raise ValueError(f"Board not found: {board_id}")
        return board

    async def get_boards(self, owner_id: str | None = None) -> list[Board]:
        """Get all boards, optionally filtered by owner.

        When owner_id is provided, returns only boards owned by that user.
        When owner_id is None, returns all boards (backward compatible).
        """
        query = select(Board)
        if owner_id is not None:
            query = query.where(Board.owner_id == owner_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_board(self, board_id: str, data: BoardUpdate) -> Board:
        """Update a board."""
        board = await self.get_board_by_id(board_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(board, field, value)

        await self.db.commit()
        await self.db.refresh(board)
        return board

    async def delete_board(self, board_id: str) -> None:
        """Delete a board and all its children (cascades)."""
        board = await self.get_board_by_id(board_id)
        await self.db.delete(board)
        await self.db.commit()

    async def initialize_board_config(self, board_id: str) -> Board:
        """Initialize config for a board that has config=null.

        This is useful for migrating existing boards that were created
        before auto-initialization was implemented.

        If board already has config, this is a no-op.
        """
        board = await self.get_board_by_id(board_id)

        if board.config is None:
            board.config = self.get_default_board_config()
            await self.db.commit()
            await self.db.refresh(board)

        return board

    async def initialize_all_board_configs(self) -> dict:
        """Initialize config for all boards that have config=null.

        Returns a summary of boards that were updated.
        """
        boards = await self.get_boards()
        updated = []
        skipped = []

        for board in boards:
            if board.config is None:
                board.config = self.get_default_board_config()
                updated.append(board.id)
            else:
                skipped.append(board.id)

        if updated:
            await self.db.commit()

        return {
            "total": len(boards),
            "updated": len(updated),
            "skipped": len(skipped),
            "updated_board_ids": updated,
        }

    async def get_repo_root(self, board_id: str) -> Path:
        """Get the repo_root path for a board.

        CRITICAL: This is the ONLY authoritative way to get a repo path.
        NEVER accept paths from client requests.
        NEVER use global config repo_root when board_id is available.
        """
        board = await self.get_board_by_id(board_id)
        return Path(board.repo_root).resolve()

    # =========================================================================
    # Authorization helpers - use these to enforce board boundaries
    # =========================================================================

    async def verify_goal_in_board(self, goal_id: str, board_id: str) -> Goal:
        """Verify a goal belongs to a board.

        Raises ValueError if goal doesn't exist or doesn't belong to board.
        """
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if not goal:
            raise ValueError(f"Goal not found: {goal_id}")

        if goal.board_id and goal.board_id != board_id:
            raise ValueError(
                f"Goal {goal_id} belongs to board {goal.board_id}, not {board_id}"
            )

        return goal

    async def verify_ticket_in_board(self, ticket_id: str, board_id: str) -> Ticket:
        """Verify a ticket belongs to a board.

        Raises ValueError if ticket doesn't exist or doesn't belong to board.
        """
        result = await self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise ValueError(f"Ticket not found: {ticket_id}")

        if ticket.board_id and ticket.board_id != board_id:
            raise ValueError(
                f"Ticket {ticket_id} belongs to board {ticket.board_id}, not {board_id}"
            )

        return ticket

    async def verify_tickets_in_board(
        self, ticket_ids: list[str], board_id: str
    ) -> list[Ticket]:
        """Verify multiple tickets belong to a board.

        Raises ValueError if any ticket doesn't exist or doesn't belong.
        """
        tickets = []
        for ticket_id in ticket_ids:
            ticket = await self.verify_ticket_in_board(ticket_id, board_id)
            tickets.append(ticket)
        return tickets

    async def verify_job_in_board(self, job_id: str, board_id: str) -> Job:
        """Verify a job belongs to a board."""
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.board_id and job.board_id != board_id:
            raise ValueError(
                f"Job {job_id} belongs to board {job.board_id}, not {board_id}"
            )

        return job

    async def verify_workspace_in_board(
        self, workspace_id: str, board_id: str
    ) -> Workspace:
        """Verify a workspace belongs to a board."""
        result = await self.db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        if workspace.board_id and workspace.board_id != board_id:
            raise ValueError(
                f"Workspace {workspace_id} belongs to board {workspace.board_id}, "
                f"not {board_id}"
            )

        return workspace

    async def verify_path_under_repo_root(
        self, path: str | Path, board_id: str
    ) -> Path:
        """Verify a path is under the board's repo_root.

        CRITICAL: Use this to validate any filesystem paths before operations.
        Prevents directory traversal attacks.
        """
        repo_root = await self.get_repo_root(board_id)
        target_path = Path(path).resolve()

        try:
            target_path.relative_to(repo_root)
        except ValueError:
            raise ValueError(
                f"Path {target_path} is not under board repo_root {repo_root}"
            )

        return target_path

    async def get_board_for_goal(self, goal_id: str) -> Board | None:
        """Get the board that owns a goal (if any)."""
        result = await self.db.execute(select(Goal).where(Goal.id == goal_id))
        goal = result.scalar_one_or_none()
        if not goal or not goal.board_id:
            return None

        return await self.get_board_by_id(goal.board_id)

    async def get_board_for_ticket(self, ticket_id: str) -> Board | None:
        """Get the board that owns a ticket (if any)."""
        result = await self.db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket or not ticket.board_id:
            return None

        return await self.get_board_by_id(ticket.board_id)
