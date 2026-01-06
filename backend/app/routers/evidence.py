"""API router for Evidence endpoints."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.evidence import Evidence
from app.services.config_service import ConfigService

router = APIRouter(prefix="/evidence", tags=["evidence"])

# Maximum log file size to read (2MB)
MAX_LOG_BYTES = 2_000_000


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


def read_artifact(repo_root: Path, relpath: str | None) -> str | None:
    """Safely read an artifact file, enforcing security constraints.

    Security Policy:
        - Rejects absolute paths
        - Resolves canonical path (follows symlinks)
        - Enforces file is under <repo_root>/.smartkanban
        - Caps file size to prevent memory exhaustion

    Args:
        repo_root: Absolute path to the repository root
        relpath: Relative path to the artifact (from DB)

    Returns:
        File content if safe and exists, None otherwise
    """
    if not relpath:
        return None

    rel = Path(relpath)

    # SECURITY: Reject absolute paths - DB should only store relative paths
    if rel.is_absolute():
        return None

    # Resolve allowed root to canonical absolute path
    allowed_root = (repo_root / ".smartkanban").resolve(strict=False)

    # Resolve target to canonical absolute path (follows symlinks)
    target = (repo_root / rel).resolve(strict=False)

    # SECURITY: Enforce target is under allowed_root using commonpath
    try:
        common = os.path.commonpath([str(target), str(allowed_root)])
    except ValueError:
        # Different drives on Windows or no common path
        return None

    if common != str(allowed_root):
        return None

    # Check file exists and is a regular file
    if not target.is_file():
        return None

    # Read with size cap to prevent memory exhaustion
    try:
        size = target.stat().st_size
        if size > MAX_LOG_BYTES:
            with target.open("rb") as f:
                data = f.read(MAX_LOG_BYTES)
            return data.decode("utf-8", errors="replace") + "\n\n[truncated]"
        return target.read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return None


def get_repo_root() -> Path:
    """Get the repository root path from config."""
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
    repo_root = get_repo_root()

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
    repo_root = get_repo_root()

    content = read_artifact(repo_root, evidence.stderr_path)
    if content is None:
        return PlainTextResponse(content="", status_code=status.HTTP_200_OK)

    return PlainTextResponse(content=content)
