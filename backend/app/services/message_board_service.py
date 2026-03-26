"""Message board service for inter-agent communication.

Provides cursor-based messaging between agents working on the same ticket.
Inspired by coral's message board pattern with per-session read cursors.
Uses SELECT FOR UPDATE on cursor reads to prevent race conditions.
"""

import logging

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.agent_team import BoardMessage, BoardMessageCursor

logger = logging.getLogger(__name__)


class MessageBoardService:
    """Manages inter-agent messaging for multi-agent ticket execution."""

    def __init__(self, db: Session):
        self.db = db

    def post_message(
        self,
        board_id: str,
        ticket_id: str,
        sender_session_id: str,
        sender_role: str,
        content: str,
    ) -> BoardMessage:
        """Post a message to the board for a ticket execution."""
        msg = BoardMessage(
            board_id=board_id,
            ticket_id=ticket_id,
            sender_session_id=sender_session_id,
            sender_role=sender_role,
            content=content,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        logger.debug(
            "Board message posted: board=%s ticket=%s role=%s",
            board_id,
            ticket_id,
            sender_role,
        )
        return msg

    def read_messages(
        self,
        board_id: str,
        ticket_id: str,
        session_id: str,
        receive_mode: str = "all",
    ) -> list[BoardMessage]:
        """Read new messages since this session's last read position.

        Returns messages posted by OTHER agents (excludes own messages).
        Advances the cursor past all messages (including own).
        Uses atomic cursor update to prevent race conditions between agents.

        Args:
            board_id: Board scope.
            ticket_id: Ticket scope.
            session_id: The reading agent's session ID.
            receive_mode: "all" for orchestrators, "mentions" for workers.
        """
        cursor = self._get_or_create_cursor(board_id, ticket_id, session_id)

        # Atomically read the cursor's last_read_id and lock the row.
        # SQLite doesn't support SELECT FOR UPDATE, so we use a
        # begin_nested() savepoint + immediate re-read to serialize access.
        try:
            self.db.begin_nested()

            # Re-read cursor within savepoint for consistent snapshot
            fresh_cursor = self.db.execute(
                select(BoardMessageCursor).where(BoardMessageCursor.id == cursor.id)
            ).scalar_one()
            read_from = fresh_cursor.last_read_id

            # Fetch new messages (excluding sender's own)
            stmt = (
                select(BoardMessage)
                .where(
                    and_(
                        BoardMessage.board_id == board_id,
                        BoardMessage.ticket_id == ticket_id,
                        BoardMessage.id > read_from,
                        BoardMessage.sender_session_id != session_id,
                    )
                )
                .order_by(BoardMessage.id.asc())
            )
            messages = list(self.db.execute(stmt).scalars().all())

            # Advance cursor past ALL messages (including own)
            latest_stmt = (
                select(BoardMessage.id)
                .where(
                    and_(
                        BoardMessage.board_id == board_id,
                        BoardMessage.ticket_id == ticket_id,
                    )
                )
                .order_by(BoardMessage.id.desc())
                .limit(1)
            )
            latest_id = self.db.execute(latest_stmt).scalar()
            if latest_id is not None and latest_id > read_from:
                fresh_cursor.last_read_id = latest_id

            self.db.commit()  # Commits the savepoint
        except Exception:
            self.db.rollback()
            logger.warning(
                "Race condition in read_messages for session %s, retrying",
                session_id,
            )
            # On conflict, re-read without savepoint (fallback)
            self.db.refresh(cursor)
            stmt = (
                select(BoardMessage)
                .where(
                    and_(
                        BoardMessage.board_id == board_id,
                        BoardMessage.ticket_id == ticket_id,
                        BoardMessage.id > cursor.last_read_id,
                        BoardMessage.sender_session_id != session_id,
                    )
                )
                .order_by(BoardMessage.id.asc())
            )
            messages = list(self.db.execute(stmt).scalars().all())

        return messages

    def check_unread(
        self,
        board_id: str,
        ticket_id: str,
        session_id: str,
    ) -> int:
        """Check how many unread messages exist for this session."""
        cursor = self._get_or_create_cursor(board_id, ticket_id, session_id)

        from sqlalchemy import func as sa_func

        stmt = (
            select(sa_func.count())
            .select_from(BoardMessage)
            .where(
                and_(
                    BoardMessage.board_id == board_id,
                    BoardMessage.ticket_id == ticket_id,
                    BoardMessage.id > cursor.last_read_id,
                    BoardMessage.sender_session_id != session_id,
                )
            )
        )
        return self.db.execute(stmt).scalar() or 0

    def get_all_messages(
        self,
        board_id: str,
        ticket_id: str,
    ) -> list[BoardMessage]:
        """Get all messages for a ticket (for UI display)."""
        stmt = (
            select(BoardMessage)
            .where(
                and_(
                    BoardMessage.board_id == board_id,
                    BoardMessage.ticket_id == ticket_id,
                )
            )
            .order_by(BoardMessage.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def subscribe(
        self,
        board_id: str,
        ticket_id: str,
        session_id: str,
    ) -> BoardMessageCursor:
        """Subscribe a session to receive messages for a ticket."""
        cursor = self._get_or_create_cursor(board_id, ticket_id, session_id)
        return cursor

    def _get_or_create_cursor(
        self,
        board_id: str,
        ticket_id: str,
        session_id: str,
    ) -> BoardMessageCursor:
        """Get or create the read cursor for this session+board+ticket."""
        stmt = select(BoardMessageCursor).where(
            and_(
                BoardMessageCursor.session_id == session_id,
                BoardMessageCursor.board_id == board_id,
                BoardMessageCursor.ticket_id == ticket_id,
            )
        )
        cursor = self.db.execute(stmt).scalar_one_or_none()
        if cursor is None:
            cursor = BoardMessageCursor(
                session_id=session_id,
                board_id=board_id,
                ticket_id=ticket_id,
                last_read_id=0,
            )
            self.db.add(cursor)
            self.db.commit()
            self.db.refresh(cursor)
        return cursor
