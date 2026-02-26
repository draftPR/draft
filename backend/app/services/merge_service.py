"""Service for merging worktree branches into the default branch."""

import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ResourceNotFoundError, ValidationError
from app.models.enums import ActorType, EventType
from app.models.evidence import Evidence, EvidenceKind
from app.models.revision import RevisionStatus
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.workspace import Workspace
from app.services.config_service import ConfigService
from app.state_machine import TicketState

logger = logging.getLogger(__name__)


class MergeStrategy(StrEnum):
    """Supported merge strategies."""

    MERGE = "merge"
    REBASE = "rebase"


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    message: str
    exit_code: int
    stdout: str
    stderr: str
    default_branch: str | None = None
    evidence_ids: dict[str, str] = field(
        default_factory=dict
    )  # stdout_id, stderr_id, meta_id
    # Warning if merge succeeded but pull was skipped/failed (local-only merge)
    pull_warning: str | None = None


class MergeService:
    """Service for merging worktree branches into the default branch.

    This service handles the git operations required to merge changes
    from an isolated worktree back into the main repository's default branch.

    Safety:
        - Only operates on worktrees under .smartkanban/worktrees/
        - Never modifies protected branches directly
        - Validates ticket is in 'done' state with approved revision
        - Captures all git output as evidence (stdout AND stderr)
        - Validates worktree is clean before merge
        - Fetches remote before merge to detect divergence
    """

    PROTECTED_BRANCHES = {"main", "master", "develop", "production", "staging"}

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config_service = ConfigService()

    async def merge_ticket(
        self,
        ticket_id: str,
        strategy: MergeStrategy = MergeStrategy.MERGE,
        delete_worktree: bool = True,
        cleanup_artifacts: bool = True,
        actor_id: str = "merge_service",
    ) -> MergeResult:
        """Merge a ticket's worktree branch into the default branch.

        Args:
            ticket_id: The UUID of the ticket
            strategy: Merge strategy (merge or rebase)
            delete_worktree: Whether to delete the worktree after merge
            cleanup_artifacts: Whether to cleanup evidence files
            actor_id: ID of the actor performing the merge

        Returns:
            MergeResult with success status and details

        Raises:
            ResourceNotFoundError: If ticket or workspace not found
            ValidationError: If ticket is not in valid state for merge
            ConflictError: If merge cannot proceed due to conflicts
        """
        # Fetch ticket with workspace and revisions
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.workspace),
                selectinload(Ticket.revisions),
            )
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Validate ticket state
        if ticket.state != TicketState.DONE.value:
            raise ValidationError(
                f"Ticket must be in 'done' state to merge. Current state: {ticket.state}"
            )

        # Validate approved revision exists
        approved_revision = next(
            (r for r in ticket.revisions if r.status == RevisionStatus.APPROVED.value),
            None,
        )
        if approved_revision is None:
            raise ValidationError("Ticket must have an approved revision to merge")

        # Validate workspace exists
        workspace = ticket.workspace
        if workspace is None or not workspace.is_active:
            raise ValidationError("Ticket has no active workspace to merge from")

        worktree_path = Path(workspace.worktree_path)
        if not worktree_path.exists():
            raise ValidationError(f"Worktree path does not exist: {worktree_path}")

        # Validate worktree is under .smartkanban/worktrees/
        repo_path = self.config_service.get_repo_root()
        smartkanban_worktrees = repo_path / ".smartkanban" / "worktrees"
        try:
            worktree_path.resolve().relative_to(smartkanban_worktrees.resolve())
        except ValueError:
            raise ValidationError(
                f"Worktree must be under .smartkanban/worktrees/: {worktree_path}"
            )

        # Detect default branch early for event payload
        default_branch = self._detect_default_branch(repo_path)

        # Record merge requested event
        await self._create_event(
            ticket_id=ticket_id,
            event_type=EventType.MERGE_REQUESTED,
            reason=f"Merge requested with strategy '{strategy.value}'",
            payload={
                "strategy": strategy.value,
                "worktree_branch": workspace.branch_name,
                "base_branch": default_branch,
                "worktree_path": str(worktree_path),
            },
            actor_id=actor_id,
        )
        await self.db.commit()

        # Perform the merge
        merge_result = await self._perform_merge(
            ticket_id=ticket_id,
            workspace=workspace,
            strategy=strategy,
            default_branch=default_branch,
        )

        if merge_result.success:
            # Record success event with full details
            payload = {
                "strategy": strategy.value,
                "worktree_branch": workspace.branch_name,
                "base_branch": default_branch,
                "exit_code": merge_result.exit_code,
                "evidence_ids": merge_result.evidence_ids,
            }
            # Include warning if merge happened without pulling latest
            if merge_result.pull_warning:
                payload["pull_warning"] = merge_result.pull_warning

            await self._create_event(
                ticket_id=ticket_id,
                event_type=EventType.MERGE_SUCCEEDED,
                reason=f"Merge succeeded: {merge_result.message}",
                payload=payload,
                actor_id=actor_id,
            )
            await self.db.commit()

            # Cleanup if requested
            if delete_worktree:
                await self._cleanup_worktree(
                    ticket_id=ticket_id,
                    workspace=workspace,
                    actor_id=actor_id,
                )
        else:
            # Record failure event with full details
            await self._create_event(
                ticket_id=ticket_id,
                event_type=EventType.MERGE_FAILED,
                reason=f"Merge failed: {merge_result.message}",
                payload={
                    "strategy": strategy.value,
                    "worktree_branch": workspace.branch_name,
                    "base_branch": default_branch,
                    "exit_code": merge_result.exit_code,
                    "evidence_ids": merge_result.evidence_ids,
                },
                actor_id=actor_id,
            )
            await self.db.commit()

        return merge_result

    async def _perform_merge(
        self,
        ticket_id: str,
        workspace: Workspace,
        strategy: MergeStrategy,
        default_branch: str,
    ) -> MergeResult:
        """Perform the actual git merge/rebase operation.

        Steps:
        1. Verify worktree has no uncommitted changes (git status --porcelain)
        2. Verify branch exists and is not protected
        3. Checkout default branch in main repo
        4. Fetch from remote (git fetch)
        5. Pull with --ff-only (configurable)
        6. Merge or rebase the worktree branch
        7. Delete branch after merge (configurable)

        Args:
            ticket_id: The ticket ID
            workspace: The workspace with worktree info
            strategy: Merge strategy
            default_branch: Pre-detected default branch name

        Returns:
            MergeResult with operation outcome
        """
        repo_path = self.config_service.get_repo_root()
        worktree_path = Path(workspace.worktree_path)
        branch_name = workspace.branch_name
        merge_config = self.config_service.get_merge_config()

        start_time = time.time()
        all_stdout = []
        all_stderr = []

        def record_output(label: str, result: subprocess.CompletedProcess) -> None:
            """Helper to record command output."""
            all_stdout.append(f"=== {label} ===\n{result.stdout}")
            if result.stderr:
                all_stderr.append(f"=== {label} ===\n{result.stderr}")

        def make_failure(message: str, exit_code: int = 1) -> MergeResult:
            """Helper to create a failure result with evidence."""
            return MergeResult(
                success=False,
                message=message,
                exit_code=exit_code,
                stdout="\n".join(all_stdout),
                stderr="\n".join(all_stderr),
                default_branch=default_branch,
            )

        try:
            # Step 1: Verify worktree has no uncommitted changes
            # NOTE: This runs in WORKTREE to check worktree status
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,  # <-- WORKTREE directory
                capture_output=True,
                text=True,
                timeout=30,
            )
            record_output("git status --porcelain (worktree)", result)

            if result.stdout.strip():
                return make_failure("Worktree has uncommitted changes")

            # Step 2: Ensure branch is not protected
            if branch_name.lower() in self.PROTECTED_BRANCHES:
                return make_failure(
                    f"Cannot merge from protected branch: {branch_name}"
                )

            # Step 3: Checkout default branch in main repo
            # NOTE: All remaining git commands run in MAIN REPO, not worktree!
            # This is critical: we merge the feature branch INTO the default branch.
            result = subprocess.run(
                ["git", "checkout", default_branch],
                cwd=repo_path,  # <-- MAIN REPO directory (NOT worktree!)
                capture_output=True,
                text=True,
                timeout=60,
            )
            record_output(f"git checkout {default_branch}", result)

            if result.returncode != 0:
                return make_failure(
                    f"Failed to checkout {default_branch}", result.returncode
                )

            # Step 4: Fetch from remote (only if remote exists)
            has_remote = self._has_remote_origin(repo_path)
            if has_remote:
                result = subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                record_output("git fetch origin", result)
                # Don't fail on fetch error - network might be down
            else:
                all_stdout.append("=== Skipping fetch (no remote 'origin') ===")

            # Step 5: Optional pull before merge (only if remote exists)
            # Explicitly specify origin and branch to avoid pulling from wrong remote
            pull_warning: str | None = None
            if merge_config.pull_before_merge and has_remote:
                result = subprocess.run(
                    ["git", "pull", "--ff-only", "origin", default_branch],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                record_output(f"git pull --ff-only origin {default_branch}", result)

                if result.returncode != 0:
                    if merge_config.require_pull_success:
                        return make_failure(
                            f"Failed to pull latest changes from origin/{default_branch} "
                            f"(require_pull_success=true). Set require_pull_success: false "
                            f"in config to allow local-only merge.",
                            result.returncode,
                        )
                    else:
                        # Pull failed but config allows continuing - track warning
                        pull_warning = (
                            f"Merged locally without pulling latest from origin/{default_branch}. "
                            f"May cause conflicts when pushing."
                        )
                        all_stderr.append(
                            f"=== WARNING: git pull failed but continuing "
                            f"(require_pull_success=false) ===\n{result.stderr}"
                        )
                        logger.warning(
                            f"Pull failed for {default_branch} but continuing due to "
                            f"require_pull_success=false: {result.stderr}"
                        )
            elif not has_remote and merge_config.pull_before_merge:
                # No remote but pull was configured - note this in warning
                pull_warning = "Merged locally (no remote 'origin' configured)."

            # Step 6: Perform merge or rebase
            if strategy == MergeStrategy.MERGE:
                result = subprocess.run(
                    [
                        "git",
                        "merge",
                        "--no-ff",
                        branch_name,
                        "-m",
                        f"Merge branch '{branch_name}'",
                    ],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                record_output(f"git merge --no-ff {branch_name}", result)
            else:  # REBASE
                result = subprocess.run(
                    ["git", "rebase", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                record_output(f"git rebase {branch_name}", result)

            if result.returncode != 0:
                # Abort merge/rebase on conflict
                abort_cmd = (
                    ["git", "merge", "--abort"]
                    if strategy == MergeStrategy.MERGE
                    else ["git", "rebase", "--abort"]
                )
                subprocess.run(
                    abort_cmd, cwd=repo_path, timeout=30, capture_output=True
                )

                return make_failure(
                    f"Merge conflict or failure during {strategy.value}",
                    result.returncode,
                )

            # Step 7: Delete branch after merge (optional)
            if merge_config.delete_branch_after_merge:
                result = subprocess.run(
                    ["git", "branch", "-d", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                record_output(f"git branch -d {branch_name}", result)

            duration_ms = int((time.time() - start_time) * 1000)

            # Create evidence records (stdout, stderr, and meta)
            evidence_ids = await self._create_merge_evidence(
                ticket_id=ticket_id,
                strategy=strategy,
                branch=branch_name,
                base_branch=default_branch,
                exit_code=0,
                duration_ms=duration_ms,
                stdout="\n".join(all_stdout),
                stderr="\n".join(all_stderr),
                repo_root=repo_path,
            )

            return MergeResult(
                success=True,
                message=f"Successfully merged branch '{branch_name}' into {default_branch}",
                exit_code=0,
                stdout="\n".join(all_stdout),
                stderr="\n".join(all_stderr),
                default_branch=default_branch,
                evidence_ids=evidence_ids,
                pull_warning=pull_warning,
            )

        except subprocess.TimeoutExpired:
            all_stderr.append("[TIMEOUT]")
            return MergeResult(
                success=False,
                message="Git operation timed out",
                exit_code=-1,
                stdout="\n".join(all_stdout),
                stderr="\n".join(all_stderr),
                default_branch=default_branch,
            )
        except Exception as e:
            logger.exception(f"Merge failed for ticket {ticket_id}")
            all_stderr.append(f"[EXCEPTION: {e}]")
            return MergeResult(
                success=False,
                message=f"Merge failed: {str(e)}",
                exit_code=-1,
                stdout="\n".join(all_stdout),
                stderr="\n".join(all_stderr),
                default_branch=default_branch,
            )

    def _has_remote_origin(self, repo_path: Path) -> bool:
        """Check if the repository has an 'origin' remote.

        Args:
            repo_path: Path to the repository

        Returns:
            True if 'origin' remote exists
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _detect_default_branch(self, repo_path: Path) -> str:
        """Detect the default branch of the repository.

        Tries:
        1. git symbolic-ref refs/remotes/origin/HEAD
        2. Fallback to 'main' if exists
        3. Fallback to 'master'

        Args:
            repo_path: Path to the repository

        Returns:
            Name of the default branch
        """
        # Try origin/HEAD (most reliable for remote-tracking repos)
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Output is like "refs/remotes/origin/main"
                ref = result.stdout.strip()
                return ref.split("/")[-1]
        except Exception:
            pass

        # Check if 'main' branch exists locally
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/heads/main"],
            cwd=repo_path,
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return "main"

        # Fallback to 'master'
        return "master"

    async def _create_merge_evidence(
        self,
        ticket_id: str,
        strategy: MergeStrategy,
        branch: str,
        base_branch: str,
        exit_code: int,
        duration_ms: int,
        stdout: str,
        stderr: str,
        repo_root: Path,
    ) -> dict[str, str]:
        """Create evidence records for the merge operation.

        Creates three evidence records:
        - MERGE_STDOUT: Combined stdout from all git commands
        - MERGE_STDERR: Combined stderr from all git commands
        - MERGE_META: JSON metadata with strategy, branches, exit_code, duration, evidence_ids

        Args:
            ticket_id: The ticket ID
            strategy: Merge strategy used
            branch: Worktree branch that was merged
            base_branch: Default branch merged into
            exit_code: Exit code of merge operation
            duration_ms: Duration in milliseconds
            stdout: Combined stdout from git commands
            stderr: Combined stderr from git commands
            repo_root: Path to repo root

        Returns:
            Dict with evidence IDs: {"stdout_id", "stderr_id", "meta_id"}
        """
        evidence_dir = repo_root / ".smartkanban" / "evidence" / "merge"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        evidence_ids = {}

        # Create stdout evidence
        stdout_id = str(uuid.uuid4())
        stdout_path = evidence_dir / f"{stdout_id}.stdout"
        stdout_path.write_text(stdout, encoding="utf-8")
        stdout_relpath = str(stdout_path.relative_to(repo_root))

        stdout_evidence = Evidence(
            id=stdout_id,
            ticket_id=ticket_id,
            job_id=stdout_id,  # Use same ID as pseudo-job reference
            kind=EvidenceKind.MERGE_STDOUT.value,
            command=f"git {strategy.value}",
            exit_code=exit_code,
            stdout_path=stdout_relpath,
            stderr_path=None,
        )
        self.db.add(stdout_evidence)
        evidence_ids["stdout_id"] = stdout_id

        # Create stderr evidence (only if there's content)
        stderr_id = str(uuid.uuid4())
        if stderr.strip():
            stderr_path = evidence_dir / f"{stderr_id}.stderr"
            stderr_path.write_text(stderr, encoding="utf-8")
            stderr_relpath = str(stderr_path.relative_to(repo_root))

            stderr_evidence = Evidence(
                id=stderr_id,
                ticket_id=ticket_id,
                job_id=stderr_id,
                kind=EvidenceKind.MERGE_STDERR.value,
                command=f"git {strategy.value}",
                exit_code=exit_code,
                stdout_path=stderr_relpath,  # stderr content stored in stdout_path field
                stderr_path=None,
            )
            self.db.add(stderr_evidence)
            evidence_ids["stderr_id"] = stderr_id

        # Create meta evidence (JSON)
        meta_id = str(uuid.uuid4())
        meta = {
            "strategy": strategy.value,
            "worktree_branch": branch,
            "base_branch": base_branch,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "success": exit_code == 0,
            "evidence_ids": {
                "stdout_id": stdout_id,
                "stderr_id": stderr_id if stderr.strip() else None,
            },
        }
        meta_path = evidence_dir / f"{meta_id}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        meta_relpath = str(meta_path.relative_to(repo_root))

        meta_evidence = Evidence(
            id=meta_id,
            ticket_id=ticket_id,
            job_id=meta_id,
            kind=EvidenceKind.MERGE_META.value,
            command="merge_metadata",
            exit_code=exit_code,
            stdout_path=meta_relpath,
            stderr_path=None,
        )
        self.db.add(meta_evidence)
        evidence_ids["meta_id"] = meta_id

        await self.db.flush()
        return evidence_ids

    async def _cleanup_worktree(
        self,
        ticket_id: str,
        workspace: Workspace,
        actor_id: str,
    ) -> None:
        """Clean up a worktree after successful merge.

        Args:
            ticket_id: The ticket ID
            workspace: The workspace to clean up
            actor_id: Actor ID for event
        """
        from app.services.cleanup_service import CleanupService

        cleanup_service = CleanupService(self.db)
        await cleanup_service.delete_worktree(
            workspace=workspace,
            ticket_id=ticket_id,
            actor_id=actor_id,
            delete_branch=True,  # Safe to delete since merge succeeded
        )

    async def _create_event(
        self,
        ticket_id: str,
        event_type: EventType,
        reason: str,
        payload: dict,
        actor_id: str,
    ) -> TicketEvent:
        """Create a ticket event.

        Args:
            ticket_id: The ticket ID
            event_type: Type of event
            reason: Reason for the event
            payload: Event payload
            actor_id: Actor ID

        Returns:
            The created TicketEvent
        """
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type=event_type.value,
            from_state=TicketState.DONE.value,
            to_state=TicketState.DONE.value,
            actor_type=ActorType.SYSTEM.value,
            actor_id=actor_id,
            reason=reason,
            payload_json=json.dumps(payload),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_merge_status(self, ticket_id: str) -> dict:
        """Get the merge status for a ticket.

        Args:
            ticket_id: The ticket ID

        Returns:
            Dict with merge status info including:
            - can_merge: Whether merge is possible
            - is_merged: Whether already merged
            - has_approved_revision: Whether approval exists
            - workspace: Worktree info if active
            - last_merge_attempt: Most recent merge event
        """
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .options(
                selectinload(Ticket.workspace),
                selectinload(Ticket.events),
                selectinload(Ticket.revisions),
            )
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ResourceNotFoundError("Ticket", ticket_id)

        # Check for merge events
        merge_events = [
            e
            for e in ticket.events
            if e.event_type
            in [
                EventType.MERGE_REQUESTED.value,
                EventType.MERGE_SUCCEEDED.value,
                EventType.MERGE_FAILED.value,
            ]
        ]

        is_merged = any(
            e.event_type == EventType.MERGE_SUCCEEDED.value for e in merge_events
        )
        last_merge_attempt = max(merge_events, key=lambda e: e.created_at, default=None)

        # Check for approved revision
        has_approved_revision = any(
            r.status == RevisionStatus.APPROVED.value for r in ticket.revisions
        )

        # Workspace info
        workspace_info = None
        if ticket.workspace and ticket.workspace.is_active:
            workspace_info = {
                "worktree_path": ticket.workspace.worktree_path,
                "branch_name": ticket.workspace.branch_name,
            }

        return {
            "ticket_id": ticket_id,
            "can_merge": (
                ticket.state == TicketState.DONE.value
                and has_approved_revision
                and workspace_info is not None
                and not is_merged
            ),
            "is_merged": is_merged,
            "has_approved_revision": has_approved_revision,
            "workspace": workspace_info,
            "last_merge_attempt": {
                "event_type": last_merge_attempt.event_type,
                "reason": last_merge_attempt.reason,
                "created_at": last_merge_attempt.created_at.isoformat(),
                "payload": last_merge_attempt.get_payload(),
            }
            if last_merge_attempt
            else None,
        }
