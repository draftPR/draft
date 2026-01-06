"""API router for Evidence endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.evidence import Evidence

router = APIRouter(prefix="/evidence", tags=["evidence"])


async def get_evidence_by_id(evidence_id: str, db: AsyncSession) -> Evidence:
    """Get evidence by ID or raise 404."""
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence with id '{evidence_id}' not found",
        )
    return evidence


def read_file_content(file_path: str | None) -> str | None:
    """Read file content if path exists."""
    if file_path is None:
        return None
    path = Path(file_path)
    if path.exists():
        try:
            return path.read_text()
        except Exception:
            return None
    return None


@router.get(
    "/{evidence_id}/stdout",
    response_class=PlainTextResponse,
    summary="Get stdout content for an evidence record",
)
async def get_evidence_stdout(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Get the stdout content for a verification command."""
    evidence = await get_evidence_by_id(evidence_id, db)

    content = read_file_content(evidence.stdout_path)
    if content is None:
        return PlainTextResponse(content="", status_code=status.HTTP_200_OK)

    return PlainTextResponse(content=content)


@router.get(
    "/{evidence_id}/stderr",
    response_class=PlainTextResponse,
    summary="Get stderr content for an evidence record",
)
async def get_evidence_stderr(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Get the stderr content for a verification command."""
    evidence = await get_evidence_by_id(evidence_id, db)

    content = read_file_content(evidence.stderr_path)
    if content is None:
        return PlainTextResponse(content="", status_code=status.HTTP_200_OK)

    return PlainTextResponse(content=content)

