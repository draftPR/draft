"""API router for Evidence endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.board import Board
from app.models.evidence import Evidence
from app.models.job import Job
from app.services.config_service import ConfigService
from app.utils.artifact_reader import read_artifact

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


async def _get_repo_root_for_evidence(
    evidence: Evidence, db: AsyncSession
) -> Path:
    """Get repo_root from the board associated with this evidence's job.

    Falls back to the global ConfigService repo_root if no board is found.
    """
    if evidence.job_id:
        job_result = await db.execute(
            select(Job).where(Job.id == evidence.job_id)
        )
        job = job_result.scalar_one_or_none()
        if job and job.board_id:
            board_result = await db.execute(
                select(Board).where(Board.id == job.board_id)
            )
            board = board_result.scalar_one_or_none()
            if board and board.repo_root:
                return Path(board.repo_root)

    # Fallback to global config
    config_service = ConfigService()
    return config_service.get_repo_root()


@router.get(
    "/{evidence_id}/stdout",
    response_class=PlainTextResponse,
    summary="Get stdout content for an evidence record",
)
async def get_evidence_stdout(
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Get the stdout content for a verification command.

    Security: Only reads files under <repo_root>/.smartkanban/
    """
    evidence = await get_evidence_by_id(evidence_id, db)
    repo_root = await _get_repo_root_for_evidence(evidence, db)

    content = read_artifact(repo_root, evidence.stdout_path)
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
    """Get the stderr content for a verification command.

    Security: Only reads files under <repo_root>/.smartkanban/
    """
    evidence = await get_evidence_by_id(evidence_id, db)
    repo_root = await _get_repo_root_for_evidence(evidence, db)

    content = read_artifact(repo_root, evidence.stderr_path)
    if content is None:
        return PlainTextResponse(content="", status_code=status.HTTP_200_OK)

    return PlainTextResponse(content=content)
