"""Service for managing Board-Repo associations."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.board import Board
from app.models.board_repo import BoardRepo
from app.models.repo import Repo


class BoardRepoService:
    """Service for managing board-repo relationships."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_repo_to_board(
        self,
        board_id: str,
        repo_id: str,
        is_primary: bool = False,
        custom_setup_script: Optional[str] = None,
        custom_cleanup_script: Optional[str] = None,
    ) -> BoardRepo:
        """
        Add a repository to a board.

        Args:
            board_id: Board UUID
            repo_id: Repo UUID
            is_primary: Whether this is the primary repo
            custom_setup_script: Per-board setup script override
            custom_cleanup_script: Per-board cleanup script override

        Returns:
            Created BoardRepo association

        Raises:
            ValueError: If board or repo not found, or association already exists
        """
        # Verify board exists
        board_result = await self.db.execute(select(Board).where(Board.id == board_id))
        board = board_result.scalar_one_or_none()
        if not board:
            raise ValueError(f"Board not found: {board_id}")

        # Verify repo exists
        repo_result = await self.db.execute(select(Repo).where(Repo.id == repo_id))
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repo not found: {repo_id}")

        # Check if association already exists
        existing_result = await self.db.execute(
            select(BoardRepo).where(
                BoardRepo.board_id == board_id, BoardRepo.repo_id == repo_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Repo {repo_id} is already associated with board {board_id}")

        # If setting as primary, unset other primary repos
        if is_primary:
            await self._unset_primary_repos(board_id)

        # Create association
        board_repo = BoardRepo(
            id=str(uuid.uuid4()),
            board_id=board_id,
            repo_id=repo_id,
            is_primary=is_primary,
            custom_setup_script=custom_setup_script,
            custom_cleanup_script=custom_cleanup_script,
        )

        self.db.add(board_repo)
        await self.db.commit()
        await self.db.refresh(board_repo)

        # Eager load repo relationship
        result = await self.db.execute(
            select(BoardRepo)
            .options(joinedload(BoardRepo.repo))
            .where(BoardRepo.id == board_repo.id)
        )
        return result.scalar_one()

    async def get_board_repos(self, board_id: str) -> list[BoardRepo]:
        """
        Get all repos associated with a board.

        Returns:
            List of BoardRepo associations with eager-loaded Repo
        """
        result = await self.db.execute(
            select(BoardRepo)
            .options(joinedload(BoardRepo.repo))
            .where(BoardRepo.board_id == board_id)
            .order_by(BoardRepo.is_primary.desc(), BoardRepo.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_board_repo(self, board_id: str, repo_id: str) -> Optional[BoardRepo]:
        """Get a specific board-repo association."""
        result = await self.db.execute(
            select(BoardRepo)
            .options(joinedload(BoardRepo.repo))
            .where(BoardRepo.board_id == board_id, BoardRepo.repo_id == repo_id)
        )
        return result.scalar_one_or_none()

    async def update_board_repo(
        self,
        board_id: str,
        repo_id: str,
        is_primary: Optional[bool] = None,
        custom_setup_script: Optional[str] = None,
        custom_cleanup_script: Optional[str] = None,
    ) -> BoardRepo:
        """
        Update a board-repo association.

        Args:
            board_id: Board UUID
            repo_id: Repo UUID
            is_primary: Whether to set as primary
            custom_setup_script: Per-board setup script override
            custom_cleanup_script: Per-board cleanup script override

        Returns:
            Updated BoardRepo

        Raises:
            ValueError: If association not found
        """
        board_repo = await self.get_board_repo(board_id, repo_id)
        if not board_repo:
            raise ValueError(
                f"Board-repo association not found: board={board_id}, repo={repo_id}"
            )

        # If setting as primary, unset other primary repos
        if is_primary is not None and is_primary and not board_repo.is_primary:
            await self._unset_primary_repos(board_id)
            board_repo.is_primary = True

        if custom_setup_script is not None:
            board_repo.custom_setup_script = custom_setup_script
        if custom_cleanup_script is not None:
            board_repo.custom_cleanup_script = custom_cleanup_script

        await self.db.commit()
        await self.db.refresh(board_repo)

        # Reload with repo relationship
        result = await self.db.execute(
            select(BoardRepo)
            .options(joinedload(BoardRepo.repo))
            .where(BoardRepo.id == board_repo.id)
        )
        return result.scalar_one()

    async def remove_repo_from_board(self, board_id: str, repo_id: str) -> None:
        """
        Remove a repo from a board.

        Args:
            board_id: Board UUID
            repo_id: Repo UUID

        Raises:
            ValueError: If association not found
        """
        board_repo = await self.get_board_repo(board_id, repo_id)
        if not board_repo:
            raise ValueError(
                f"Board-repo association not found: board={board_id}, repo={repo_id}"
            )

        await self.db.delete(board_repo)
        await self.db.commit()

    async def _unset_primary_repos(self, board_id: str) -> None:
        """Unset is_primary for all repos on a board."""
        result = await self.db.execute(
            select(BoardRepo).where(
                BoardRepo.board_id == board_id, BoardRepo.is_primary == True
            )
        )
        primary_repos = list(result.scalars().all())

        for board_repo in primary_repos:
            board_repo.is_primary = False

        await self.db.flush()
