"""Complete split parents: merge DONE sub-tickets back into the parent branch.

Runs from the sync planner tick, outside the planner lock. For each parent
that is BLOCKED because it was split and whose children are all DONE:

1. ensure the parent worktree exists (recreated from its branch if cleaned)
2. `git merge --no-ff` each child branch into the parent branch, in split order
3. record the merged diff as a revision on a synthetic job so it is reviewable
4. transition the parent to VERIFYING (verify job auto-enqueued)
5. clean up the children's worktrees and branches

A failed merge is recorded as a COMMENT event on the parent (payload
`split_merge_failed`) and retried after SPLIT_MERGE_RETRY_MINUTES.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, select

from app.database_sync import get_sync_db
from app.models.board import Board
from app.models.job import Job, JobKind, JobStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.git_ops import merge_branch
from app.services.workspace_service import WorkspaceService
from app.state_machine import ActorType, EventType, TicketState

logger = logging.getLogger(__name__)

SPLIT_MERGE_RETRY_MINUTES = 30
_FAILURE_MARKER = '"split_merge_failed": true'


def find_ready_split_parents(db) -> list[tuple[str, list[str]]]:
    """Return (parent_id, child_ids in split order) for parents ready to merge."""
    parent_ids = (
        select(Ticket.parent_ticket_id)
        .where(Ticket.parent_ticket_id.isnot(None))
        .distinct()
    )
    parents = (
        db.execute(
            select(Ticket).where(
                and_(
                    Ticket.state == TicketState.BLOCKED.value,
                    Ticket.id.in_(parent_ids),
                )
            )
        )
        .scalars()
        .all()
    )

    ready: list[tuple[str, list[str]]] = []
    for parent in parents:
        children = (
            db.execute(
                select(Ticket)
                .where(Ticket.parent_ticket_id == parent.id)
                .order_by(Ticket.sort_order.asc().nullslast(), Ticket.created_at)
            )
            .scalars()
            .all()
        )
        if not children:
            continue
        if any(c.state != TicketState.DONE.value for c in children):
            continue
        if _failed_recently(db, parent.id):
            continue
        ready.append((parent.id, [c.id for c in children]))
    return ready


def _failed_recently(db, parent_id: str) -> bool:
    last = db.execute(
        select(TicketEvent.created_at)
        .where(
            and_(
                TicketEvent.ticket_id == parent_id,
                TicketEvent.payload_json.like(f"%{_FAILURE_MARKER}%"),
            )
        )
        .order_by(TicketEvent.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return datetime.now(UTC) - last < timedelta(minutes=SPLIT_MERGE_RETRY_MINUTES)


def _record_failure(
    db, parent_id: str, message: str, files: list[str] | None = None
) -> None:
    db.add(
        TicketEvent(
            ticket_id=parent_id,
            event_type=EventType.COMMENT.value,
            from_state=TicketState.BLOCKED.value,
            to_state=TicketState.BLOCKED.value,
            actor_type=ActorType.PLANNER.value,
            actor_id="planner",
            reason=f"Sub-ticket merge failed: {message}",
            payload_json=json.dumps(
                {"split_merge_failed": True, "conflicted_files": files or []}
            ),
        )
    )
    db.commit()
    logger.warning("Split merge failed for parent %s: %s", parent_id, message)


def complete_split_parents_sync() -> int:
    """Merge children into every ready parent. Returns parents completed."""
    with get_sync_db() as db:
        ready = find_ready_split_parents(db)

    completed = 0
    for parent_id, child_ids in ready:
        try:
            if _merge_children_into_parent(parent_id, child_ids):
                completed += 1
        except Exception:
            logger.exception("Failed to complete split parent %s", parent_id)
    return completed


def _merge_children_into_parent(parent_id: str, child_ids: list[str]) -> bool:
    # Worker helpers: local import, worker imports the planner tick module.
    from app.data_dir import get_evidence_dir
    from app.models.evidence import EvidenceKind
    from app.worker import (
        capture_git_diff,
        create_evidence_record,
        create_revision_for_job,
        transition_ticket_sync,
    )

    with get_sync_db() as db:
        parent = db.get(Ticket, parent_id)
        if parent is None:
            return False
        ws = WorkspaceService(db)
        try:
            parent_ws = ws.ensure_workspace(parent.id, parent.goal_id)
            db.commit()
        except Exception as exc:
            _record_failure(db, parent_id, f"cannot open parent worktree: {exc}")
            return False

        worktree = Path(parent_ws.worktree_path)
        board = db.get(Board, parent.board_id) if parent.board_id else None
        repo_root = (
            Path(board.repo_root)
            if board and board.repo_root
            else WorkspaceService.get_repo_path()
        )

        merged: list[str] = []
        for cid in child_ids:
            child = db.get(Ticket, cid)
            child_ws = ws.get_workspace_by_ticket_id(cid)
            if child is None or child_ws is None:
                _record_failure(db, parent_id, f"sub-ticket {cid} has no branch")
                return False
            result = merge_branch(
                worktree, child_ws.branch_name, f"Merge sub-ticket: {child.title}"
            )
            if not result.success:
                _record_failure(
                    db,
                    parent_id,
                    f"'{child.title}': {result.message}",
                    result.conflicted_files,
                )
                return False
            merged.append(child.title)

        # Synthetic job so the merged diff shows up as a reviewable revision.
        now = datetime.now(UTC)
        job = Job(
            ticket_id=parent_id,
            board_id=parent.board_id,
            kind=JobKind.EXECUTE.value,
            status=JobStatus.SUCCEEDED.value,
            started_at=now,
            finished_at=now,
            exit_code=0,
        )
        db.add(job)
        db.commit()
        job_id = job.id

    evidence_dir = get_evidence_dir(job_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stat_id, patch_id = str(uuid.uuid4()), str(uuid.uuid4())
    exit_code, stat_path, patch_path, _stat, _has_changes = capture_git_diff(
        cwd=worktree,
        evidence_dir=evidence_dir,
        evidence_id=stat_id,
        repo_root=repo_root,
    )
    create_evidence_record(
        ticket_id=parent_id,
        job_id=job_id,
        command="git diff --stat",
        exit_code=exit_code,
        stdout_path=stat_path,
        stderr_path="",
        evidence_id=stat_id,
        kind=EvidenceKind.GIT_DIFF_STAT,
    )
    create_evidence_record(
        ticket_id=parent_id,
        job_id=job_id,
        command="git diff",
        exit_code=exit_code,
        stdout_path=patch_path,
        stderr_path="",
        evidence_id=patch_id,
        kind=EvidenceKind.GIT_DIFF_PATCH,
    )
    name_status_file = evidence_dir / f"{stat_id}.name_status"
    if name_status_file.exists():
        create_evidence_record(
            ticket_id=parent_id,
            job_id=job_id,
            command="git diff --name-status",
            exit_code=0,
            stdout_path=str(name_status_file),
            stderr_path="",
            evidence_id=str(uuid.uuid4()),
            kind=EvidenceKind.GIT_NAME_STATUS,
        )
    create_revision_for_job(
        ticket_id=parent_id,
        job_id=job_id,
        diff_stat_evidence_id=stat_id,
        diff_patch_evidence_id=patch_id,
    )
    transition_ticket_sync(
        parent_id,
        TicketState.VERIFYING,
        reason=f"Merged {len(merged)} sub-tickets into parent branch",
        payload={"split_children": child_ids, "merged": merged},
        actor_id="planner",
        auto_verify=True,
    )

    # Children are merged; release their worktrees and branches.
    with get_sync_db() as db:
        ws = WorkspaceService(db)
        for cid in child_ids:
            try:
                ws.cleanup_worktree(cid)
            except Exception as exc:
                logger.warning("Cleanup of sub-ticket %s failed: %s", cid, exc)
        db.commit()

    logger.info("Split parent %s: merged %d sub-tickets", parent_id, len(merged))
    return True
