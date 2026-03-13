"""Service layer for Review operations (comments and summaries)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ResourceNotFoundError, ValidationError
from app.models.review_comment import AuthorType, ReviewComment
from app.models.review_summary import ReviewDecision, ReviewSummary
from app.models.revision import Revision, RevisionStatus
from app.schemas.review import FeedbackBundle, FeedbackComment
from app.services.revision_service import compute_anchor

logger = logging.getLogger(__name__)


class ReviewService:
    """Service class for Review business logic (comments and summaries)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Comment Operations ====================

    async def add_comment(
        self,
        revision_id: str,
        file_path: str,
        line_number: int,
        body: str,
        author_type: AuthorType = AuthorType.HUMAN,
        hunk_header: str | None = None,
        line_content: str | None = None,
    ) -> ReviewComment:
        """Add an inline comment to a revision.

        Args:
            revision_id: The UUID of the revision
            file_path: Path to the file being commented on
            line_number: Line number in the new file
            body: Comment body text
            author_type: Type of author (human, agent, system)
            hunk_header: Optional diff hunk header for anchor computation
            line_content: Optional line content for anchor computation

        Returns:
            The created ReviewComment instance

        Raises:
            ResourceNotFoundError: If revision not found
            ConflictError: If revision is superseded
        """
        # Verify revision exists
        result = await self.db.execute(
            select(Revision).where(Revision.id == revision_id)
        )
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ResourceNotFoundError("Revision", revision_id)

        # Block comments on superseded revisions
        if revision.status == RevisionStatus.SUPERSEDED.value:
            from app.exceptions import ConflictError

            raise ConflictError(
                "Revision is superseded. Please review the latest revision."
            )

        # Compute anchor - use provided values or fallback
        anchor = compute_anchor(
            file_path=file_path,
            hunk_header=hunk_header or "",
            line_content=line_content or f"line:{line_number}",
        )

        comment = ReviewComment(
            revision_id=revision_id,
            file_path=file_path,
            line_number=line_number,
            anchor=anchor,
            line_content=line_content,
            body=body,
            author_type=author_type.value,
            resolved=False,
        )
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment)

        logger.info(
            f"Added comment {comment.id} on revision {revision_id} at {file_path}:{line_number}"
        )
        return comment

    async def get_comments_for_revision(
        self, revision_id: str, include_resolved: bool = True
    ) -> list[ReviewComment]:
        """Get all comments for a revision.

        Args:
            revision_id: The UUID of the revision
            include_resolved: Whether to include resolved comments

        Returns:
            List of ReviewComment instances ordered by creation time
        """
        # Verify revision exists
        result = await self.db.execute(
            select(Revision).where(Revision.id == revision_id)
        )
        if result.scalar_one_or_none() is None:
            raise ResourceNotFoundError("Revision", revision_id)

        query = select(ReviewComment).where(ReviewComment.revision_id == revision_id)

        if not include_resolved:
            query = query.where(ReviewComment.resolved == False)  # noqa: E712

        query = query.order_by(ReviewComment.created_at.asc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_comment_by_id(self, comment_id: str) -> ReviewComment:
        """Get a comment by its ID.

        Args:
            comment_id: The UUID of the comment

        Returns:
            The ReviewComment instance

        Raises:
            ResourceNotFoundError: If the comment is not found
        """
        result = await self.db.execute(
            select(ReviewComment).where(ReviewComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if comment is None:
            raise ResourceNotFoundError("ReviewComment", comment_id)
        return comment

    async def resolve_comment(self, comment_id: str) -> ReviewComment:
        """Mark a comment as resolved.

        Args:
            comment_id: The UUID of the comment

        Returns:
            The updated ReviewComment instance
        """
        comment = await self.get_comment_by_id(comment_id)
        comment.resolved = True
        await self.db.flush()
        await self.db.refresh(comment)
        logger.info(f"Resolved comment {comment_id}")
        return comment

    async def unresolve_comment(self, comment_id: str) -> ReviewComment:
        """Mark a comment as unresolved.

        Args:
            comment_id: The UUID of the comment

        Returns:
            The updated ReviewComment instance
        """
        comment = await self.get_comment_by_id(comment_id)
        comment.resolved = False
        await self.db.flush()
        await self.db.refresh(comment)
        logger.info(f"Unresolved comment {comment_id}")
        return comment

    async def get_unresolved_count(self, revision_id: str) -> int:
        """Get the count of unresolved comments for a revision.

        Args:
            revision_id: The UUID of the revision

        Returns:
            Number of unresolved comments
        """
        result = await self.db.execute(
            select(ReviewComment).where(
                ReviewComment.revision_id == revision_id,
                ReviewComment.resolved == False,  # noqa: E712
            )
        )
        return len(list(result.scalars().all()))

    # ==================== Review Summary Operations ====================

    async def submit_review(
        self,
        revision_id: str,
        decision: ReviewDecision,
        summary: str,
    ) -> ReviewSummary:
        """Submit a review decision for a revision.

        Args:
            revision_id: The UUID of the revision
            decision: The review decision (approved or changes_requested)
            summary: High-level review feedback

        Returns:
            The created ReviewSummary instance

        Raises:
            ValidationError: If unresolved comments exist when approving
            ConflictError: If revision is superseded
        """
        # Get revision with comments
        result = await self.db.execute(
            select(Revision)
            .where(Revision.id == revision_id)
            .options(
                selectinload(Revision.comments),
                selectinload(Revision.review_summary),
            )
        )
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ResourceNotFoundError("Revision", revision_id)

        # Block reviews on superseded revisions
        if revision.status == RevisionStatus.SUPERSEDED.value:
            from app.exceptions import ConflictError

            raise ConflictError(
                "Revision is superseded. Please review the latest revision."
            )

        # Check if review already exists
        if revision.review_summary:
            raise ValidationError("This revision already has a review submitted")

        # Note: We allow approval even with unresolved comments.
        # Comments are informational notes; approving accepts the changes.
        # Requesting changes sends all unresolved comments to the agent as feedback.

        # Create the review summary
        review_summary = ReviewSummary(
            revision_id=revision_id,
            decision=decision.value,
            body=summary,
        )
        self.db.add(review_summary)

        # Update revision status based on decision
        if decision == ReviewDecision.APPROVED:
            revision.status = RevisionStatus.APPROVED.value
        else:
            revision.status = RevisionStatus.CHANGES_REQUESTED.value

        await self.db.flush()
        await self.db.refresh(review_summary)

        logger.info(f"Submitted review for revision {revision_id}: {decision.value}")
        return review_summary

    async def get_review_summary(self, revision_id: str) -> ReviewSummary | None:
        """Get the review summary for a revision.

        Args:
            revision_id: The UUID of the revision

        Returns:
            The ReviewSummary instance or None if no review exists
        """
        result = await self.db.execute(
            select(ReviewSummary).where(ReviewSummary.revision_id == revision_id)
        )
        return result.scalar_one_or_none()

    # ==================== Feedback Bundle ====================

    async def get_feedback_bundle(self, revision_id: str) -> FeedbackBundle:
        """Get the feedback bundle for a revision.

        This is the structured feedback that gets injected into the agent prompt
        when creating a new revision after changes are requested.

        Args:
            revision_id: The UUID of the revision

        Returns:
            FeedbackBundle containing all review feedback
        """
        # Get revision with all related data
        result = await self.db.execute(
            select(Revision)
            .where(Revision.id == revision_id)
            .options(
                selectinload(Revision.comments),
                selectinload(Revision.review_summary),
            )
        )
        revision = result.scalar_one_or_none()
        if revision is None:
            raise ResourceNotFoundError("Revision", revision_id)

        # Build feedback comments (only unresolved ones are actionable)
        feedback_comments = [
            FeedbackComment(
                file_path=comment.file_path,
                line_number=comment.line_number,
                anchor=comment.anchor,
                body=comment.body,
                line_content=comment.line_content,
            )
            for comment in revision.comments
            if not comment.resolved
        ]

        # Get review summary
        summary_text = ""
        decision_text = "pending"
        if revision.review_summary:
            summary_text = revision.review_summary.body
            decision_text = revision.review_summary.decision

        return FeedbackBundle(
            ticket_id=revision.ticket_id,
            revision_id=revision_id,
            revision_number=revision.number,
            decision=decision_text,
            summary=summary_text,
            comments=feedback_comments,
        )
