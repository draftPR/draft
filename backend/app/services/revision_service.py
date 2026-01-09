"""Service layer for Revision operations."""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ResourceNotFoundError
from app.models.evidence import Evidence, EvidenceKind
from app.models.revision import Revision, RevisionStatus
from app.models.ticket import Ticket
from app.services.config_service import ConfigService
from app.utils.artifact_reader import read_artifact

logger = logging.getLogger(__name__)


def compute_anchor(file_path: str, hunk_header: str, line_content: str) -> str:
    """Compute stable anchor using sha1.

    The anchor is a hash of the file path, hunk header, and line content.
    This allows comments to survive small line shifts between revisions,
    as long as the hunk context and line content remain similar.

    Args:
        file_path: Path to the file being commented on
        hunk_header: Diff hunk header (e.g., '@@ -10,5 +10,7 @@')
        line_content: Content of the line being commented on

    Returns:
        Truncated sha1 hex digest (16 characters)
    """
    content = f"{file_path}::{hunk_header}::{line_content}"
    return hashlib.sha1(content.encode()).hexdigest()[:16]


class RevisionService:
    """Service class for Revision business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_revision(
        self,
        ticket_id: str,
        job_id: str,
        diff_stat_evidence_id: str | None = None,
        diff_patch_evidence_id: str | None = None,
    ) -> Revision:
        """Create a new revision for a ticket.

        Automatically:
        - Supersedes any existing open revision for the ticket
        - Increments the revision number

        Args:
            ticket_id: The UUID of the ticket
            job_id: The UUID of the job that produced this revision
            diff_stat_evidence_id: Optional evidence ID for git diff stat
            diff_patch_evidence_id: Optional evidence ID for git diff patch

        Returns:
            The created Revision instance
        """
        # First supersede any open revisions
        await self.supersede_open_revisions(ticket_id)

        # Get the next revision number
        next_number = await self._get_next_revision_number(ticket_id)

        # Create the new revision
        revision = Revision(
            ticket_id=ticket_id,
            job_id=job_id,
            number=next_number,
            status=RevisionStatus.OPEN.value,
            diff_stat_evidence_id=diff_stat_evidence_id,
            diff_patch_evidence_id=diff_patch_evidence_id,
        )
        self.db.add(revision)
        await self.db.flush()
        await self.db.refresh(revision)

        logger.info(f"Created revision {revision.id} (#{next_number}) for ticket {ticket_id}")
        return revision

    async def _get_next_revision_number(self, ticket_id: str) -> int:
        """Get the next revision number for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            The next revision number (1-based)
        """
        result = await self.db.execute(
            select(Revision.number)
            .where(Revision.ticket_id == ticket_id)
            .order_by(Revision.number.desc())
            .limit(1)
        )
        last_number = result.scalar_one_or_none()
        return (last_number or 0) + 1

    async def supersede_open_revisions(self, ticket_id: str) -> int:
        """Mark all open revisions for a ticket as superseded.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            Number of revisions superseded
        """
        result = await self.db.execute(
            select(Revision)
            .where(
                Revision.ticket_id == ticket_id,
                Revision.status == RevisionStatus.OPEN.value,
            )
        )
        open_revisions = list(result.scalars().all())

        for revision in open_revisions:
            revision.status = RevisionStatus.SUPERSEDED.value
            logger.info(f"Superseded revision {revision.id} (#{revision.number})")

        return len(open_revisions)

    async def get_revision_by_id(self, revision_id: str) -> Revision:
        """Get a revision by its ID with all related data.

        Args:
            revision_id: The UUID of the revision

        Returns:
            The Revision instance with comments and review_summary loaded

        Raises:
            ResourceNotFoundError: If the revision is not found
        """
        result = await self.db.execute(
            select(Revision)
            .where(Revision.id == revision_id)
            .options(
                selectinload(Revision.comments),
                selectinload(Revision.review_summary),
                selectinload(Revision.diff_stat_evidence),
                selectinload(Revision.diff_patch_evidence),
            )
        )
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ResourceNotFoundError("Revision", revision_id)
        return revision

    async def get_revisions_for_ticket(self, ticket_id: str) -> list[Revision]:
        """Get all revisions for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            List of Revision instances ordered by number descending

        Raises:
            ResourceNotFoundError: If the ticket is not found
        """
        # Verify ticket exists
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        if result.scalar_one_or_none() is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        result = await self.db.execute(
            select(Revision)
            .where(Revision.ticket_id == ticket_id)
            .options(selectinload(Revision.comments))
            .order_by(Revision.number.desc())
        )
        return list(result.scalars().all())

    async def get_latest_revision(self, ticket_id: str) -> Revision | None:
        """Get the latest (open) revision for a ticket.

        Args:
            ticket_id: The UUID of the ticket

        Returns:
            The latest open Revision or None if no open revision exists
        """
        result = await self.db.execute(
            select(Revision)
            .where(
                Revision.ticket_id == ticket_id,
                Revision.status == RevisionStatus.OPEN.value,
            )
            .options(
                selectinload(Revision.comments),
                selectinload(Revision.review_summary),
            )
            .order_by(Revision.number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_revision_status(
        self, revision_id: str, status: RevisionStatus
    ) -> Revision:
        """Update the status of a revision.

        Args:
            revision_id: The UUID of the revision
            status: The new status

        Returns:
            The updated Revision instance
        """
        revision = await self.get_revision_by_id(revision_id)
        revision.status = status.value
        await self.db.flush()
        await self.db.refresh(revision)
        return revision

    async def get_revision_diff(self, revision_id: str) -> tuple[str | None, str | None]:
        """Get the diff content for a revision (both stat and patch).

        Args:
            revision_id: The UUID of the revision

        Returns:
            Tuple of (diff_stat, diff_patch) content strings
        """
        revision = await self.get_revision_by_id(revision_id)

        diff_stat = None
        diff_patch = None

        if revision.diff_stat_evidence:
            diff_stat = await self._read_evidence_content(revision.diff_stat_evidence)

        if revision.diff_patch_evidence:
            diff_patch = await self._read_evidence_content(revision.diff_patch_evidence)

        return diff_stat, diff_patch

    async def get_revision_diff_summary(self, revision_id: str) -> str | None:
        """Get only the diff stat (summary) for a revision.

        This is the lightweight call for the file list view.

        Args:
            revision_id: The UUID of the revision

        Returns:
            diff_stat content string or None
        """
        revision = await self.get_revision_by_id(revision_id)

        if revision.diff_stat_evidence:
            return await self._read_evidence_content(revision.diff_stat_evidence)
        return None

    async def get_revision_diff_patch(self, revision_id: str) -> str | None:
        """Get only the diff patch (heavy content) for a revision.

        This is the heavyweight call - only fetch when user opens diff viewer.

        Args:
            revision_id: The UUID of the revision

        Returns:
            diff_patch content string or None
        """
        revision = await self.get_revision_by_id(revision_id)

        if revision.diff_patch_evidence:
            return await self._read_evidence_content(revision.diff_patch_evidence)
        return None

    async def _read_evidence_content(self, evidence: Evidence) -> str | None:
        """Read the content of an evidence file.

        SECURITY: Uses read_artifact() which enforces:
        - File must be under <repo_root>/.smartkanban
        - No path traversal attacks
        - Size limits

        Args:
            evidence: The Evidence instance

        Returns:
            The content string or None if not readable
        """
        if not evidence.stdout_path:
            return None

        try:
            config_service = ConfigService()
            repo_root = config_service.get_repo_root()
            return read_artifact(repo_root, evidence.stdout_path)
        except Exception as e:
            logger.warning(f"Failed to read evidence content from {evidence.stdout_path}: {e}")
            return None

    async def find_diff_evidence_for_job(
        self, job_id: str
    ) -> tuple[str | None, str | None]:
        """Find diff stat and patch evidence IDs for a job.

        Args:
            job_id: The UUID of the job

        Returns:
            Tuple of (diff_stat_evidence_id, diff_patch_evidence_id)
        """
        # Find diff stat evidence
        stat_result = await self.db.execute(
            select(Evidence)
            .where(
                Evidence.job_id == job_id,
                Evidence.kind == EvidenceKind.GIT_DIFF_STAT.value,
            )
            .order_by(Evidence.created_at.desc())
            .limit(1)
        )
        stat_evidence = stat_result.scalar_one_or_none()

        # Find diff patch evidence
        patch_result = await self.db.execute(
            select(Evidence)
            .where(
                Evidence.job_id == job_id,
                Evidence.kind == EvidenceKind.GIT_DIFF_PATCH.value,
            )
            .order_by(Evidence.created_at.desc())
            .limit(1)
        )
        patch_evidence = patch_result.scalar_one_or_none()

        return (
            stat_evidence.id if stat_evidence else None,
            patch_evidence.id if patch_evidence else None,
        )

