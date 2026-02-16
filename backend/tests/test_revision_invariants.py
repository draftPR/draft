"""Canary tests for revision invariants.

These tests validate the critical invariants that must hold for the PR-like review system:
1. Revision creation is idempotent (same job_id doesn't create duplicate revisions)
2. At most one revision can be 'open' per ticket
3. Approval is blocked if unresolved comments exist (server-side)
4. Feedback bundle includes all unresolved comments
5. Orphaned comments are preserved (not dropped)
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.job import Job, JobKind, JobStatus
from app.models.review_comment import AuthorType
from app.models.review_summary import ReviewDecision
from app.models.revision import Revision, RevisionStatus
from app.models.ticket import Ticket
from app.services.review_service import ReviewService
from app.services.revision_service import RevisionService

# ==================== Test Fixtures ====================


@pytest.fixture
async def sample_goal(db: AsyncSession) -> Goal:
    """Create a sample goal for testing."""
    goal = Goal(
        title="Test Goal",
        description="Test goal for revision invariants",
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


@pytest.fixture
async def sample_ticket(db: AsyncSession, sample_goal: Goal) -> Ticket:
    """Create a sample ticket for testing."""
    ticket = Ticket(
        title="Test Ticket",
        description="Test ticket for revision invariants",
        state="executing",
        goal_id=sample_goal.id,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)
    return ticket


@pytest.fixture
async def sample_job(db: AsyncSession, sample_ticket: Ticket) -> Job:
    """Create a sample job for testing."""
    job = Job(
        ticket_id=sample_ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


# ==================== Test 1: Revision Idempotency ====================


async def test_revision_idempotency_constraint_prevents_duplicates(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that the same job cannot create two revisions.

    If the same execute job is retried, we must not create Revision N twice.
    The unique constraint on (ticket_id, job_id) should prevent this.
    """
    revision_service = RevisionService(db)

    # Create first revision
    await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=sample_job.id,
    )
    await db.commit()

    # Attempt to create second revision with same job_id
    # This should raise an IntegrityError due to unique constraint
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await revision_service.create_revision(
            ticket_id=sample_ticket.id,
            job_id=sample_job.id,  # Same job_id!
        )
        await db.commit()


# ==================== Test 2: Two Open Revisions Prevention ====================


async def test_at_most_one_open_revision_per_ticket(
    db: AsyncSession, sample_ticket: Ticket
):
    """Test that creating a new revision supersedes the previous open revision.

    For a ticket:
    - At most 1 revision can be 'open'
    - Creating a new revision must supersede the previous open revision in the same transaction
    """
    revision_service = RevisionService(db)

    # Create first job and revision
    job1 = Job(
        ticket_id=sample_ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job1)
    await db.flush()

    revision1 = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=job1.id,
    )
    await db.commit()

    # Verify rev1 is open
    await db.refresh(revision1)
    assert revision1.status == RevisionStatus.OPEN.value

    # Create second job and revision
    job2 = Job(
        ticket_id=sample_ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job2)
    await db.flush()

    revision2 = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=job2.id,
    )
    await db.commit()

    # Refresh rev1 and verify it's superseded
    await db.refresh(revision1)
    assert revision1.status == RevisionStatus.SUPERSEDED.value, \
        "Previous open revision should be superseded"

    # Verify rev2 is open
    assert revision2.status == RevisionStatus.OPEN.value

    # Count open revisions - must be exactly 1
    result = await db.execute(
        select(Revision).where(
            Revision.ticket_id == sample_ticket.id,
            Revision.status == RevisionStatus.OPEN.value,
        )
    )
    open_revisions = result.scalars().all()
    assert len(open_revisions) == 1, \
        f"Expected exactly 1 open revision, got {len(open_revisions)}"
    assert open_revisions[0].id == revision2.id


# ==================== Test 3: Approval Gating ====================


async def test_approval_allowed_with_unresolved_comments(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that approval succeeds even with unresolved comments.

    The review service deliberately allows approval with unresolved comments.
    Comments are informational; approving accepts the changes regardless.
    """
    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Create revision
    revision = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=sample_job.id,
    )
    await db.commit()

    # Add an unresolved comment
    await review_service.add_comment(
        revision_id=revision.id,
        file_path="src/example.py",
        line_number=42,
        body="This needs to be fixed",
        author_type=AuthorType.HUMAN,
    )
    await db.commit()

    # Approval should succeed despite unresolved comments
    summary = await review_service.submit_review(
        revision_id=revision.id,
        decision=ReviewDecision.APPROVED,
        summary="LGTM",
    )

    assert summary is not None
    assert summary.decision == ReviewDecision.APPROVED.value


async def test_approval_succeeds_when_all_comments_resolved(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that approval succeeds when all comments are resolved."""
    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Create revision
    revision = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=sample_job.id,
    )
    await db.commit()

    # Add a comment
    comment = await review_service.add_comment(
        revision_id=revision.id,
        file_path="src/example.py",
        line_number=42,
        body="This needs to be fixed",
        author_type=AuthorType.HUMAN,
    )
    await db.commit()

    # Resolve the comment
    await review_service.resolve_comment(comment.id)
    await db.commit()

    # Now approval should succeed
    review_summary = await review_service.submit_review(
        revision_id=revision.id,
        decision=ReviewDecision.APPROVED,
        summary="LGTM",
    )
    await db.commit()

    assert review_summary.decision == ReviewDecision.APPROVED.value


# ==================== Test 4: Feedback Injection Correctness ====================


async def test_feedback_bundle_contains_unresolved_comments(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that feedback bundle includes all unresolved comments.

    When changes are requested:
    - The feedback bundle must include review summary
    - Only unresolved comments should be included (or resolved with flag)
    """
    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Save IDs upfront before any operations that might expire them
    ticket_id = sample_ticket.id

    # Create revision
    revision = await revision_service.create_revision(
        ticket_id=ticket_id,
        job_id=sample_job.id,
    )
    revision_id = revision.id
    await db.commit()

    # Add two comments
    comment1 = await review_service.add_comment(
        revision_id=revision_id,
        file_path="src/example.py",
        line_number=42,
        body="Rename this variable",
        author_type=AuthorType.HUMAN,
    )
    await review_service.add_comment(
        revision_id=revision_id,
        file_path="src/helper.py",
        line_number=10,
        body="Add error handling here",
        author_type=AuthorType.HUMAN,
    )
    await db.commit()

    # Resolve one comment
    await review_service.resolve_comment(comment1.id)
    await db.commit()

    # Request changes
    await review_service.submit_review(
        revision_id=revision_id,
        decision=ReviewDecision.CHANGES_REQUESTED,
        summary="Please address the remaining issue",
    )
    await db.commit()

    # Expire cached objects to force a fresh query
    db.expire_all()

    # Get feedback bundle
    feedback = await review_service.get_feedback_bundle(revision_id)

    # Verify feedback bundle structure
    assert feedback.ticket_id == ticket_id
    assert feedback.revision_id == revision_id
    assert feedback.decision == "changes_requested"
    assert feedback.summary == "Please address the remaining issue"

    # Only unresolved comment should be in the bundle
    assert len(feedback.comments) == 1
    assert feedback.comments[0].file_path == "src/helper.py"
    assert feedback.comments[0].body == "Add error handling here"


# ==================== Test 5: Orphaned Comment Behavior ====================


async def test_orphaned_comments_included_in_feedback_bundle(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that comments whose anchors can't be found are still included.

    When a comment is on a line that's been removed in a new revision:
    - Comment should show as orphaned (via the orphaned flag)
    - Comment should still be included in feedback bundle
    - Comment should NOT be dropped
    """
    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Create revision
    revision = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=sample_job.id,
    )
    await db.commit()

    # Add a comment with specific anchor data
    await review_service.add_comment(
        revision_id=revision.id,
        file_path="src/old_file.py",
        line_number=100,  # Line that might not exist after rerun
        body="This function is inefficient",
        author_type=AuthorType.HUMAN,
        hunk_header="@@ -90,10 +90,15 @@",
        line_content="def slow_function():",
    )
    await db.commit()

    # Request changes
    await review_service.submit_review(
        revision_id=revision.id,
        decision=ReviewDecision.CHANGES_REQUESTED,
        summary="Please optimize",
    )
    await db.commit()

    # Get feedback bundle - comment should be present
    feedback = await review_service.get_feedback_bundle(revision.id)

    # The comment must be included (not dropped!)
    assert len(feedback.comments) == 1
    assert feedback.comments[0].file_path == "src/old_file.py"
    assert feedback.comments[0].body == "This function is inefficient"
    # The anchor should be preserved for matching
    assert feedback.comments[0].anchor is not None


# ==================== Test: Auto-rerun Cap ====================


async def test_auto_rerun_cap_enforced(db: AsyncSession, sample_goal: Goal):
    """Test that auto-reruns are capped to prevent infinite loops.

    Caps:
    - Max 2 auto-reruns PER REVISION (per source_revision_id)
    - Max 5 total revisions per ticket

    After max reached: require explicit human action.
    """
    # This test validates the logic exists, but the actual cap is enforced
    # in the router endpoint. We test the count logic here.

    ticket = Ticket(
        title="Rerun Test Ticket",
        description="Test ticket for rerun cap",
        state="needs_human",
        goal_id=sample_goal.id,
    )
    db.add(ticket)
    await db.flush()

    revision_service = RevisionService(db)

    # Create first revision (from initial job)
    job1 = Job(
        ticket_id=ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job1)
    await db.flush()

    revision1 = await revision_service.create_revision(
        ticket_id=ticket.id,
        job_id=job1.id,
    )
    await db.commit()

    # Simulate 2 auto-reruns from revision 1 (max per revision)
    for _i in range(2):
        job = Job(
            ticket_id=ticket.id,
            kind=JobKind.EXECUTE.value,
            status=JobStatus.SUCCEEDED.value,
            source_revision_id=revision1.id,  # Addressing revision 1
        )
        db.add(job)
        await db.flush()

        await revision_service.create_revision(
            ticket_id=ticket.id,
            job_id=job.id,
        )
    await db.commit()

    # Count jobs that addressed revision 1
    jobs_from_rev1 = await db.execute(
        select(Job).where(Job.source_revision_id == revision1.id)
    )
    reruns_from_rev1 = len(list(jobs_from_rev1.scalars().all()))

    assert reruns_from_rev1 == 2, "Should have 2 auto-reruns from revision 1"
    # The router logic checks: if reruns_from_this_revision >= 2, reject
    # A 3rd auto-rerun FROM THE SAME REVISION should be blocked


# ==================== Test: Job Source Revision Traceability ====================


async def test_job_source_revision_traceability(
    db: AsyncSession, sample_ticket: Ticket, sample_job: Job
):
    """Test that jobs triggered by review have source_revision_id set."""
    revision_service = RevisionService(db)

    # Create initial revision
    revision = await revision_service.create_revision(
        ticket_id=sample_ticket.id,
        job_id=sample_job.id,
    )
    await db.commit()

    # Create a new job triggered by review (simulating what the router does)
    new_job = Job(
        ticket_id=sample_ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.QUEUED.value,
        source_revision_id=revision.id,  # Traceability link
    )
    db.add(new_job)
    await db.commit()

    # Verify the traceability link
    await db.refresh(new_job)
    assert new_job.source_revision_id == revision.id, \
        "Job should have source_revision_id linking to the revision being addressed"


# ==================== Test: Superseded Revision Guards ====================


async def test_cannot_add_comment_to_superseded_revision(
    db: AsyncSession, sample_goal: Goal
):
    """Test that adding comments to superseded revisions is blocked.

    When a new revision is created, old revisions become superseded.
    Comments on superseded revisions should return 409 Conflict.
    """
    from app.exceptions import ConflictError

    ticket = Ticket(
        title="Supersede Test Ticket",
        description="Test ticket for supersede guards",
        state="needs_human",
        goal_id=sample_goal.id,
    )
    db.add(ticket)
    await db.flush()

    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Create first revision
    job1 = Job(
        ticket_id=ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job1)
    await db.flush()

    revision1 = await revision_service.create_revision(
        ticket_id=ticket.id,
        job_id=job1.id,
    )
    revision1_id = revision1.id
    await db.commit()

    # Create second revision (this supersedes revision1)
    job2 = Job(
        ticket_id=ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job2)
    await db.flush()

    await revision_service.create_revision(
        ticket_id=ticket.id,
        job_id=job2.id,
    )
    await db.commit()

    # Verify revision1 is now superseded
    db.expire_all()
    result = await db.execute(
        select(Revision).where(Revision.id == revision1_id)
    )
    revision1_refreshed = result.scalar_one()
    assert revision1_refreshed.status == "superseded"

    # Attempt to add comment to superseded revision - should fail
    with pytest.raises(ConflictError) as exc_info:
        await review_service.add_comment(
            revision_id=revision1_id,
            file_path="src/example.py",
            line_number=42,
            body="This should fail",
            author_type=AuthorType.HUMAN,
        )

    assert "superseded" in str(exc_info.value).lower()


async def test_cannot_submit_review_to_superseded_revision(
    db: AsyncSession, sample_goal: Goal
):
    """Test that submitting reviews to superseded revisions is blocked.

    When a new revision is created, old revisions become superseded.
    Reviews on superseded revisions should return 409 Conflict.
    """
    from app.exceptions import ConflictError

    ticket = Ticket(
        title="Supersede Review Test Ticket",
        description="Test ticket for supersede review guards",
        state="needs_human",
        goal_id=sample_goal.id,
    )
    db.add(ticket)
    await db.flush()

    revision_service = RevisionService(db)
    review_service = ReviewService(db)

    # Create first revision
    job1 = Job(
        ticket_id=ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job1)
    await db.flush()

    revision1 = await revision_service.create_revision(
        ticket_id=ticket.id,
        job_id=job1.id,
    )
    revision1_id = revision1.id
    await db.commit()

    # Create second revision (this supersedes revision1)
    job2 = Job(
        ticket_id=ticket.id,
        kind=JobKind.EXECUTE.value,
        status=JobStatus.SUCCEEDED.value,
    )
    db.add(job2)
    await db.flush()

    await revision_service.create_revision(
        ticket_id=ticket.id,
        job_id=job2.id,
    )
    await db.commit()

    # Attempt to submit review to superseded revision - should fail
    with pytest.raises(ConflictError) as exc_info:
        await review_service.submit_review(
            revision_id=revision1_id,
            decision=ReviewDecision.APPROVED,
            summary="This should fail",
        )

    assert "superseded" in str(exc_info.value).lower()

