"""Tests for AutonomyService safety checks and auto-actions."""

import uuid

from sqlalchemy import select

from app.models.enums import ActorType
from app.models.evidence import Evidence, EvidenceKind
from app.models.goal import Goal
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.autonomy_service import AutonomyService
from app.services.config_service import AutonomyConfig
from app.state_machine import TicketState

# ── Fixtures ──


def make_goal(
    autonomy_enabled: bool = True,
    auto_approve_tickets: bool = True,
    auto_approve_revisions: bool = True,
    auto_merge: bool = True,
    auto_approve_followups: bool = True,
    max_auto_approvals: int | None = None,
    auto_approval_count: int = 0,
) -> Goal:
    """Create a Goal with autonomy settings."""
    return Goal(
        id=str(uuid.uuid4()),
        title="Test Goal",
        description="Test goal for autonomy",
        autonomy_enabled=autonomy_enabled,
        auto_approve_tickets=auto_approve_tickets,
        auto_approve_revisions=auto_approve_revisions,
        auto_merge=auto_merge,
        auto_approve_followups=auto_approve_followups,
        max_auto_approvals=max_auto_approvals,
        auto_approval_count=auto_approval_count,
    )


def make_ticket(goal: Goal, state: str = "verifying") -> Ticket:
    """Create a Ticket linked to a goal."""
    return Ticket(
        id=str(uuid.uuid4()),
        goal_id=goal.id,
        title="Test Ticket",
        description="Test ticket",
        state=state,
    )


def make_evidence(
    ticket_id: str,
    kind: str = EvidenceKind.VERIFY_META.value,
    exit_code: int = 0,
    stdout_path: str = "test.txt",
) -> Evidence:
    """Create an Evidence record."""
    return Evidence(
        id=str(uuid.uuid4()),
        ticket_id=ticket_id,
        job_id=str(uuid.uuid4()),
        kind=kind,
        command="test",
        exit_code=exit_code,
        stdout_path=stdout_path,
    )


# ── can_auto_approve_ticket tests ──


async def test_auto_approve_ticket_all_checks_pass(db):
    """Auto-approve ticket when all goal settings are enabled."""
    goal = make_goal()
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_ticket(db, ticket)

    assert result.approved is True
    assert "allowed" in result.reason


async def test_auto_approve_ticket_autonomy_disabled(db):
    """Reject when autonomy_enabled is False."""
    goal = make_goal(autonomy_enabled=False)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_ticket(db, ticket)

    assert result.approved is False
    assert "not enabled" in result.reason


async def test_auto_approve_ticket_feature_disabled(db):
    """Reject when auto_approve_tickets is False."""
    goal = make_goal(auto_approve_tickets=False)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_ticket(db, ticket)

    assert result.approved is False
    assert "not enabled" in result.reason


async def test_auto_approve_ticket_max_approvals_reached(db):
    """Reject when max_auto_approvals is reached."""
    goal = make_goal(max_auto_approvals=2, auto_approval_count=2)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_ticket(db, ticket)

    assert result.approved is False
    assert "Max auto-approvals" in result.reason


async def test_auto_approve_ticket_under_max_approvals(db):
    """Allow when auto_approval_count is under max."""
    goal = make_goal(max_auto_approvals=5, auto_approval_count=3)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_ticket(db, ticket)

    assert result.approved is True


# ── can_auto_approve_revision tests ──


async def test_auto_approve_revision_all_checks_pass(db):
    """Auto-approve revision when all checks pass."""
    goal = make_goal()
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal)
    db.add(ticket)
    await db.flush()

    # Add passing verification evidence
    evidence = make_evidence(ticket.id, kind=EvidenceKind.VERIFY_META.value, exit_code=0)
    db.add(evidence)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_revision(db, ticket)

    assert result.approved is True


async def test_auto_approve_revision_verification_failed(db):
    """Reject when verification evidence has non-zero exit code."""
    goal = make_goal()
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal)
    db.add(ticket)
    await db.flush()

    # Add failing verification evidence
    evidence = make_evidence(ticket.id, kind=EvidenceKind.VERIFY_META.value, exit_code=1)
    db.add(evidence)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_revision(db, ticket)

    assert result.approved is False
    assert "Verification failed" in result.reason


async def test_auto_approve_revision_autonomy_disabled(db):
    """Reject when autonomy is not enabled on goal."""
    goal = make_goal(autonomy_enabled=False)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal)
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_revision(db, ticket)

    assert result.approved is False


async def test_auto_approve_revision_feature_disabled(db):
    """Reject when auto_approve_revisions is False."""
    goal = make_goal(auto_approve_revisions=False)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal)
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_revision(db, ticket)

    assert result.approved is False
    assert "not enabled" in result.reason


async def test_auto_approve_revision_max_approvals_reached(db):
    """Reject when max auto-approvals has been reached."""
    goal = make_goal(max_auto_approvals=1, auto_approval_count=1)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal)
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    result = await service.can_auto_approve_revision(db, ticket)

    assert result.approved is False
    assert "Max auto-approvals" in result.reason


# ── Diff size and sensitive file tests (unit-level, no file I/O) ──


def test_check_revision_approval_passes_basic():
    """Pure logic check: revision approval with passing goal and no evidence."""
    goal = make_goal()
    config = AutonomyConfig()
    service = AutonomyService(config=config)

    result = service._check_revision_approval(goal, [])
    assert result.approved is True


def test_check_revision_approval_verification_fail():
    """Pure logic check: verify evidence with bad exit code blocks approval."""
    goal = make_goal()
    ticket = make_ticket(goal)
    evidence = make_evidence(ticket.id, kind=EvidenceKind.VERIFY_META.value, exit_code=1)

    config = AutonomyConfig(require_verification_pass=True)
    service = AutonomyService(config=config)

    result = service._check_revision_approval(goal, [evidence])
    assert result.approved is False
    assert "Verification failed" in result.reason


def test_check_revision_approval_verification_pass_not_required():
    """When require_verification_pass is False, failing verify does not block."""
    goal = make_goal()
    ticket = make_ticket(goal)
    evidence = make_evidence(ticket.id, kind=EvidenceKind.VERIFY_META.value, exit_code=1)

    config = AutonomyConfig(require_verification_pass=False)
    service = AutonomyService(config=config)

    result = service._check_revision_approval(goal, [evidence])
    assert result.approved is True


def test_check_ticket_approval_all_enabled():
    """Pure logic: ticket approval passes with all flags on."""
    goal = make_goal()
    service = AutonomyService(config=AutonomyConfig())
    result = service._check_ticket_approval(goal)
    assert result.approved is True


def test_check_ticket_approval_max_exceeded():
    """Pure logic: ticket approval fails when count >= max."""
    goal = make_goal(max_auto_approvals=3, auto_approval_count=3)
    service = AutonomyService(config=AutonomyConfig())
    result = service._check_ticket_approval(goal)
    assert result.approved is False


def test_check_ticket_approval_no_max():
    """Pure logic: no max means unlimited approvals."""
    goal = make_goal(max_auto_approvals=None, auto_approval_count=100)
    service = AutonomyService(config=AutonomyConfig())
    result = service._check_ticket_approval(goal)
    assert result.approved is True


# ── record_auto_action tests ──


async def test_record_auto_action_creates_event(db):
    """Record auto-action creates a TicketEvent and increments counter."""
    goal = make_goal(auto_approval_count=0)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="verifying")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    await service.record_auto_action(
        db,
        ticket,
        action_type="approve_revision",
        details={"reason": "All checks passed"},
        from_state="verifying",
        to_state="done",
    )
    await db.flush()

    # Check event was created
    result = await db.execute(
        select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
    )
    events = list(result.scalars().all())
    assert len(events) == 1
    assert events[0].actor_type == ActorType.SYSTEM.value
    assert events[0].actor_id == "autonomy_service"
    assert "approve_revision" in events[0].reason

    # Check counter incremented
    await db.refresh(goal)
    assert goal.auto_approval_count == 1


async def test_record_auto_action_increments_counter(db):
    """Multiple auto-actions increment the counter correctly."""
    goal = make_goal(auto_approval_count=5)
    db.add(goal)
    await db.flush()

    ticket = make_ticket(goal, state="proposed")
    db.add(ticket)
    await db.flush()

    service = AutonomyService(config=AutonomyConfig())
    await service.record_auto_action(
        db, ticket, "approve_ticket", {"reason": "test"}
    )
    await db.flush()
    await db.refresh(goal)

    assert goal.auto_approval_count == 6


# ── State machine transition test ──


def test_verifying_to_done_transition_allowed():
    """VERIFYING -> DONE should be allowed in the state machine."""
    from app.state_machine import validate_transition

    assert validate_transition(TicketState.VERIFYING, TicketState.DONE) is True
