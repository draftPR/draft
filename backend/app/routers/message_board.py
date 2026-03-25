"""API router for the inter-agent message board.

Provides REST endpoints for agents to post, read, and check messages
during multi-agent ticket execution. Also used by the frontend to
display the team chat view.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/boards/{board_id}/messages", tags=["message-board"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PostMessageRequest(BaseModel):
    ticket_id: str
    session_id: str
    sender_role: str = ""
    content: str


class MessageResponse(BaseModel):
    id: int
    board_id: str
    ticket_id: str
    sender_session_id: str
    sender_role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    unread: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def post_message(
    board_id: str,
    body: PostMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Post a message to the team board for a ticket execution.

    Called by agents via the board CLI during multi-agent execution.
    """

    from app.models.agent_team import BoardMessage

    msg = BoardMessage(
        board_id=board_id,
        ticket_id=body.ticket_id,
        sender_session_id=body.session_id,
        sender_role=body.sender_role,
        content=body.content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


@router.get("", response_model=list[MessageResponse])
async def read_messages(
    board_id: str,
    ticket_id: str = Query(...),
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Read new messages since this session's last read position.

    Advances the cursor past returned messages. Excludes the caller's
    own messages from the result but still advances past them.
    """
    from sqlalchemy import and_
    from sqlalchemy import select as sa_select

    from app.models.agent_team import BoardMessage, BoardMessageCursor

    # Get or create cursor
    cursor_stmt = sa_select(BoardMessageCursor).where(
        and_(
            BoardMessageCursor.session_id == session_id,
            BoardMessageCursor.board_id == board_id,
            BoardMessageCursor.ticket_id == ticket_id,
        )
    )
    cursor_result = await db.execute(cursor_stmt)
    cursor = cursor_result.scalar_one_or_none()
    if cursor is None:
        cursor = BoardMessageCursor(
            session_id=session_id,
            board_id=board_id,
            ticket_id=ticket_id,
            last_read_id=0,
        )
        db.add(cursor)
        await db.flush()

    # Fetch new messages from others
    msg_stmt = (
        sa_select(BoardMessage)
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
    msg_result = await db.execute(msg_stmt)
    messages = list(msg_result.scalars().all())

    # Advance cursor past ALL messages (including own)
    latest_stmt = (
        sa_select(BoardMessage.id)
        .where(
            and_(
                BoardMessage.board_id == board_id,
                BoardMessage.ticket_id == ticket_id,
            )
        )
        .order_by(BoardMessage.id.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_stmt)
    latest_id = latest_result.scalar()
    if latest_id is not None and latest_id > cursor.last_read_id:
        cursor.last_read_id = latest_id

    await db.commit()
    return messages


@router.get("/check", response_model=UnreadCountResponse)
async def check_unread(
    board_id: str,
    ticket_id: str = Query(...),
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Check how many unread messages exist for this session."""
    from sqlalchemy import and_, func
    from sqlalchemy import select as sa_select

    from app.models.agent_team import BoardMessage, BoardMessageCursor

    cursor_stmt = sa_select(BoardMessageCursor).where(
        and_(
            BoardMessageCursor.session_id == session_id,
            BoardMessageCursor.board_id == board_id,
            BoardMessageCursor.ticket_id == ticket_id,
        )
    )
    cursor_result = await db.execute(cursor_stmt)
    cursor = cursor_result.scalar_one_or_none()
    last_read = cursor.last_read_id if cursor else 0

    count_stmt = (
        sa_select(func.count())
        .select_from(BoardMessage)
        .where(
            and_(
                BoardMessage.board_id == board_id,
                BoardMessage.ticket_id == ticket_id,
                BoardMessage.id > last_read,
                BoardMessage.sender_session_id != session_id,
            )
        )
    )
    count_result = await db.execute(count_stmt)
    unread = count_result.scalar() or 0
    return UnreadCountResponse(unread=unread)


@router.get("/all", response_model=list[MessageResponse])
async def get_all_messages(
    board_id: str,
    ticket_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages for a ticket execution (for UI display)."""
    from sqlalchemy import and_
    from sqlalchemy import select as sa_select

    from app.models.agent_team import BoardMessage

    stmt = (
        sa_select(BoardMessage)
        .where(
            and_(
                BoardMessage.board_id == board_id,
                BoardMessage.ticket_id == ticket_id,
            )
        )
        .order_by(BoardMessage.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
