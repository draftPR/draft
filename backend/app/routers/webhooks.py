"""Router for webhook configuration (CRUD on Board.config.webhooks)."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.board import Board
from app.services.config_service import deep_merge_dicts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# --- Schemas ---


class WebhookCreate(BaseModel):
    url: str = Field(..., description="URL to POST webhook payloads to")
    events: list[str] = Field(
        default=["*"],
        description='Event filter list. Use ["*"] for all events.',
    )
    secret: str | None = Field(
        None, description="Optional HMAC-SHA256 secret for payload signing"
    )


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    has_secret: bool


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookResponse]
    board_id: str


# --- Helpers ---


async def _resolve_board(db: AsyncSession, board_id: str | None) -> Board:
    if board_id:
        result = await db.execute(select(Board).where(Board.id == board_id))
        board = result.scalar_one_or_none()
        if not board:
            raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
        return board
    result = await db.execute(select(Board).limit(1))
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=400, detail="No boards exist.")
    return board


def _get_webhooks(board: Board) -> list[dict]:
    config = board.config or {}
    return config.get("webhooks", [])


def _set_webhooks(board: Board, webhooks: list[dict]) -> None:
    config = board.config or {}
    config["webhooks"] = webhooks
    board.config = config


def _to_response(wh: dict) -> WebhookResponse:
    return WebhookResponse(
        id=wh["id"],
        url=wh["url"],
        events=wh.get("events", ["*"]),
        has_secret=bool(wh.get("secret")),
    )


# --- Endpoints ---


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    board_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all webhooks configured for a board."""
    board = await _resolve_board(db, board_id)
    webhooks = _get_webhooks(board)
    return WebhookListResponse(
        webhooks=[_to_response(wh) for wh in webhooks],
        board_id=board.id,
    )


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    data: WebhookCreate,
    board_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Add a new webhook to a board."""
    board = await _resolve_board(db, board_id)
    webhooks = _get_webhooks(board)

    wh = {
        "id": str(uuid.uuid4()),
        "url": data.url,
        "events": data.events,
    }
    if data.secret:
        wh["secret"] = data.secret

    webhooks.append(wh)
    _set_webhooks(board, webhooks)
    await db.commit()
    await db.refresh(board)

    logger.info("Webhook created: id=%s url=%s board=%s", wh["id"], wh["url"], board.id)
    return _to_response(wh)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    board_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Remove a webhook from a board."""
    board = await _resolve_board(db, board_id)
    webhooks = _get_webhooks(board)
    original_len = len(webhooks)
    webhooks = [wh for wh in webhooks if wh.get("id") != webhook_id]

    if len(webhooks) == original_len:
        raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")

    _set_webhooks(board, webhooks)
    await db.commit()
    logger.info("Webhook deleted: id=%s board=%s", webhook_id, board.id)
