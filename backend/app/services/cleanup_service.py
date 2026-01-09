"""Service for cleaning up worktrees and evidence files."""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ActorType, EventType
from app.models.evidence import Evidence
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.workspace import Workspace
from app.services.config_service import ConfigService
from app.state_machine import TicketState

# Event type constants - use enum values for consistency
MERGE_SUCCEEDED_EVENT = EventType.MERGE_SUCCEEDED.value
MERGE_REQUESTED_EVENT = EventType.MERGE_REQUESTED.value

logger = logging.getLogger(__name__)


# Ticket states that should NOT have their worktrees deleted
PROTECTED_TICKET_STATES = {
    TicketState.EXECUTING.value,
    TicketState.VERIFYING.value,
    TicketState.NEEDS_HUMAN.value,
}


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    worktrees_deleted: int = 0
    worktrees_failed: int = 0
    worktrees_skipped: int = 0
    evidence_files_deleted: int = 0
    evidence_files_failed: int = 0
    bytes_freed: int = 0
    details: list[str] = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


def _sanitize_output(text: str | None, max_length: int = 500) -> str | None:
    """Sanitize git output for safe JSON storage.

    Removes null bytes, carriage returns, and control characters that could
    break JSON/logging or cause odd rendering in UI.

    Args:
        text: Raw output text (may contain control chars)
        max_length: Maximum length to keep

    Returns:
        Sanitized text or None if input was None
    """
    if text is None:
        return None
    # Remove null bytes, carriage returns (\r), and most control characters
    # Keep only newlines (\n) and tabs (\t) as whitespace
    sanitized = "".join(
        c for c in text
        if c == "\n" or c == "\t" or (ord(c) >= 32 and ord(c) != 127)
        # Note: \r (ord 13) is excluded since it's < 32 and not \n or \t
    )
    return sanitized[:max_length] if len(sanitized) > max_length else sanitized


class CleanupService:
    """Service for cleaning up worktrees and evidence files.

    Safety:
        - Only deletes paths under .smartkanban/
        - Uses `git worktree remove` + `git worktree prune` (not shutil)
        - Never deletes worktrees for tickets in executing/verifying/needs_human
        - Validates paths before deletion
        - Creates audit events for deletions
        - Verifies branch is actually merged via git before deletion
        - Hard guard: refuses if worktree path equals main repo path
    """

    SMARTKANBAN_DIR = ".smartkanban"
    WORKTREES_DIR = ".smartkanban/worktrees"
    EVIDENCE_DIR = ".smartkanban/evidence"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.config_service = ConfigService()

    def _detect_default_branch(self, repo_path: Path) -> str:
        """Detect the default branch of the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            Name of the default branch (main, master, etc.)
        """
        # Try origin/HEAD first
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip().split("/")[-1]
        except Exception:
            pass

        # Check if 'main' exists locally
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "refs/heads/main"],
            cwd=repo_path,
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return "main"

        return "master"

    def _ref_exists(self, ref: str, repo_path: Path) -> bool:
        """Check if a git ref exists.

        Args:
            ref: Full ref path (e.g., refs/heads/main)
            repo_path: Path to the repository

        Returns:
            True if ref exists
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _is_branch_ancestor_of(
        self, branch_name: str, target_branch: str, repo_path: Path
    ) -> tuple[bool, str]:
        """Check if branch is an ancestor of target branch using git merge-base.

        Uses explicit refs (refs/heads/<branch>) to avoid ambiguity with tags,
        remote refs, or detached HEAD states.

        Args:
            branch_name: The branch to check (e.g., feature branch)
            target_branch: The branch to check against (e.g., main)
            repo_path: Path to the repository

        Returns:
            Tuple of (is_ancestor, reason_if_not)
        """
        feature_ref = f"refs/heads/{branch_name}"
        target_ref = f"refs/heads/{target_branch}"

        # Verify both refs exist before checking ancestry
        if not self._ref_exists(feature_ref, repo_path):
            return False, f"Branch ref {feature_ref} does not exist"

        if not self._ref_exists(target_ref, repo_path):
            return False, f"Target branch ref {target_ref} does not exist"

        try:
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", feature_ref, target_ref],
                cwd=repo_path,
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, ""
            else:
                return False, f"{feature_ref} is not an ancestor of {target_ref}"
        except Exception as e:
            return False, f"merge-base check failed: {e}"

    def _is_registered_worktree(self, path: Path, repo_path: Path) -> bool:
        """Check if a path is registered as a git worktree.

        Uses proper Path resolution and comparison (not string matching)
        to handle trailing slashes, symlinks, and relative paths.

        Safety: Only considers paths under .smartkanban/worktrees/ as valid
        worktrees for this check.

        Args:
            path: Path to check
            repo_path: Repository root

        Returns:
            True if path is listed in `git worktree list`
        """
        try:
            # Resolve and normalize the path we're checking
            check_path = path.resolve()

            # Safety: Validate check_path is under .smartkanban/worktrees/
            smartkanban_worktrees = (repo_path / self.WORKTREES_DIR).resolve()
            try:
                check_path.relative_to(smartkanban_worktrees)
            except ValueError:
                # Path is not under .smartkanban/worktrees/ - not a valid worktree for us
                logger.warning(
                    f"Path {check_path} is not under {smartkanban_worktrees}, "
                    f"not checking worktree registration"
                )
                return False

            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return True  # Assume registered if we can't check (safer)

            # Parse porcelain output - each worktree block starts with "worktree <path>"
            for line in result.stdout.splitlines():
                if line.startswith("worktree "):
                    # Extract path after "worktree " prefix
                    registered_path_str = line[9:].strip()
                    # Resolve to handle symlinks, trailing slashes, etc.
                    try:
                        registered_path = Path(registered_path_str).resolve()
                        if registered_path == check_path:
                            return True
                    except (OSError, ValueError):
                        # Invalid path in worktree list - skip
                        continue
            return False
        except Exception as e:
            logger.warning(f"Failed to check worktree registration for {path}: {e}")
            return True  # Assume registered if check fails (safer)

    async def delete_worktree(
        self,
        workspace: Workspace,
        ticket_id: str,
        actor_id: str = "cleanup_service",
        force: bool = False,
        delete_branch: bool = False,
    ) -> bool:
        """Delete a single worktree using git worktree remove.

        Steps:
        1. Validate path is under .smartkanban/worktrees/
        2. Run `git worktree remove --force <path>`
        3. Run `git worktree prune` to clean up stale entries
        4. Delete branch ONLY if merge succeeded or delete_branch=True
        5. Mark workspace as cleaned up in DB
        6. Create cleanup event

        Args:
            workspace: The workspace to delete
            ticket_id: The ticket ID
            actor_id: Actor ID for event
            force: If True, skip ticket state check (use with caution)
            delete_branch: If True, force-delete the branch even if not merged

        Returns:
            True if deletion succeeded
        """
        repo_path = self.config_service.get_repo_root()
        worktree_path = Path(workspace.worktree_path)

        # Resolve paths canonically for consistent comparison
        resolved_worktree = worktree_path.resolve()
        resolved_repo = repo_path.resolve()
        resolved_smartkanban = (repo_path / self.WORKTREES_DIR).resolve()

        # HARD GUARD: Never allow deletion of the main repo itself
        # Even if symlink weirdness makes it appear under .smartkanban/worktrees
        # Check 1: worktree equals repo
        # Check 2 (belt-and-suspenders): repo is under worktree (worktree is parent of repo)
        worktree_is_repo = resolved_worktree == resolved_repo
        repo_is_under_worktree = False
        try:
            # If repo is relative to worktree, then worktree is a parent of repo
            # This should NEVER be true - if it is, something is very wrong
            repo_is_under_worktree = resolved_repo.is_relative_to(resolved_worktree)
        except (ValueError, TypeError):
            pass  # Not relative, which is expected

        if worktree_is_repo or repo_is_under_worktree:
            failure_reason = (
                "worktree path equals main repo path"
                if worktree_is_repo
                else "worktree path is parent of main repo (would delete repo)"
            )
            logger.critical(
                f"CRITICAL: Refusing to delete! worktree={resolved_worktree}, "
                f"repo={resolved_repo}, equals={worktree_is_repo}, "
                f"repo_under_worktree={repo_is_under_worktree}"
            )
            event = TicketEvent(
                ticket_id=ticket_id,
                event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                from_state=None,
                to_state=None,
                actor_type=ActorType.SYSTEM.value,
                actor_id=actor_id,
                reason=f"CRITICAL: Worktree cleanup BLOCKED - {failure_reason}",
                payload_json=json.dumps({
                    "worktree_path": str(worktree_path),
                    "resolved_worktree": str(resolved_worktree),
                    "resolved_repo": str(resolved_repo),
                    "cleanup_failed": True,
                    "failure_reason": f"CRITICAL: {failure_reason}",
                    "branch_name": workspace.branch_name,
                    "worktree_equals_repo": worktree_is_repo,
                    "repo_is_under_worktree": repo_is_under_worktree,
                }),
            )
            self.db.add(event)
            await self.db.flush()
            return False

        # Safety: validate path is under .smartkanban/worktrees/
        try:
            resolved_worktree.relative_to(resolved_smartkanban)
        except ValueError:
            logger.error(f"Refusing to delete worktree not under {self.WORKTREES_DIR}: {worktree_path}")
            event = TicketEvent(
                ticket_id=ticket_id,
                event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                from_state=None,
                to_state=None,
                actor_type=ActorType.SYSTEM.value,
                actor_id=actor_id,
                reason=f"Worktree cleanup REFUSED: path not under {self.WORKTREES_DIR}",
                payload_json=json.dumps({
                    "worktree_path": str(worktree_path),
                    "cleanup_failed": True,
                    "failure_reason": f"Path validation failed: not under {self.WORKTREES_DIR}",
                    "branch_name": workspace.branch_name,
                }),
            )
            self.db.add(event)
            await self.db.flush()
            return False

        # Check ticket state (unless force=True)
        ticket = None
        if not force:
            ticket_result = await self.db.execute(
                select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.events))
            )
            ticket = ticket_result.scalar_one_or_none()
            if ticket and ticket.state in PROTECTED_TICKET_STATES:
                logger.warning(
                    f"Refusing to delete worktree for ticket {ticket_id} in state {ticket.state}"
                )
                event = TicketEvent(
                    ticket_id=ticket_id,
                    event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                    from_state=None,
                    to_state=None,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=actor_id,
                    reason=f"Worktree cleanup REFUSED: ticket in protected state {ticket.state}",
                    payload_json=json.dumps({
                        "worktree_path": str(worktree_path),
                        "cleanup_failed": True,
                        "failure_reason": f"Ticket in protected state: {ticket.state}",
                        "branch_name": workspace.branch_name,
                    }),
                )
                self.db.add(event)
                await self.db.flush()
                return False

        # Check for merge events and extract base_branch from payload
        # Look at both MERGE_SUCCEEDED and MERGE_REQUESTED to find base_branch
        # This ensures we can verify even if events were pruned or merge failed
        branch_merged = False
        merge_base_branch: str | None = None

        if not ticket:
            # Fetch ticket if not already loaded
            ticket_result = await self.db.execute(
                select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.events))
            )
            ticket = ticket_result.scalar_one_or_none()

        if ticket:
            # First pass: look for MERGE_SUCCEEDED (definitive)
            for event in ticket.events:
                if event.event_type == MERGE_SUCCEEDED_EVENT:
                    branch_merged = True
                    try:
                        payload = json.loads(event.payload_json) if event.payload_json else {}
                        merge_base_branch = payload.get("base_branch")
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        pass  # Invalid JSON - continue without base_branch
                    break

            # Second pass: if no base_branch yet, look in MERGE_REQUESTED
            if not merge_base_branch:
                for event in ticket.events:
                    if event.event_type == MERGE_REQUESTED_EVENT:
                        try:
                            payload = json.loads(event.payload_json) if event.payload_json else {}
                            merge_base_branch = payload.get("base_branch")
                            if merge_base_branch:
                                break  # Found it
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            pass  # Invalid JSON - continue

        # =====================================================================
        # STEP 1: DECIDE branch deletion BEFORE worktree removal
        # This ensures we have full git context for the ancestry check
        # =====================================================================
        should_delete_branch = False
        branch_skip_reason = None
        git_verification_reason = None
        used_base_branch: str | None = None

        if delete_branch:
            # Force deletion requested - skip safety checks
            should_delete_branch = True
            logger.info(f"Will force-delete branch {workspace.branch_name} (delete_branch=True)")
        elif branch_merged:
            # Event says merged - verify with git using explicit refs
            # PREFER the base_branch from merge event (consistency), fallback to detection
            if merge_base_branch:
                used_base_branch = merge_base_branch
                logger.info(f"Using base_branch from merge event: {used_base_branch}")
            else:
                used_base_branch = self._detect_default_branch(repo_path)
                logger.warning(
                    f"Merge event missing base_branch, falling back to detection: {used_base_branch}"
                )

            git_verified, git_verification_reason = self._is_branch_ancestor_of(
                workspace.branch_name, used_base_branch, repo_path
            )

            if git_verified:
                should_delete_branch = True
                logger.info(
                    f"Branch {workspace.branch_name} verified as ancestor of {used_base_branch}"
                )
            else:
                # Event says merged but git disagrees - DO NOT DELETE
                branch_skip_reason = (
                    f"Event claims merged but git verification failed: {git_verification_reason}"
                )
                logger.warning(f"NOT deleting branch {workspace.branch_name}: {branch_skip_reason}")
        else:
            branch_skip_reason = "No merge event found"
            logger.info(f"Keeping branch {workspace.branch_name}: {branch_skip_reason}")

        try:
            # =====================================================================
            # STEP 2: Remove worktree via git
            # =====================================================================
            worktree_removed = False
            worktree_remove_error: str | None = None
            still_registered = False

            if worktree_path.exists():
                result = subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode == 0:
                    worktree_removed = True
                else:
                    worktree_remove_error = result.stderr.strip()
                    logger.warning(
                        f"git worktree remove failed for {worktree_path}: {worktree_remove_error}"
                    )
                    # SAFE FALLBACK: Only rmtree if NOT registered as worktree
                    # This prevents corrupting git state
                    if worktree_path.exists():
                        still_registered = self._is_registered_worktree(worktree_path, repo_path)
                        # Get worktree list for debugging
                        worktree_list_result = subprocess.run(
                            ["git", "worktree", "list"],
                            cwd=repo_path,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        worktree_list_excerpt = worktree_list_result.stdout[:500] if worktree_list_result.returncode == 0 else None

                        if still_registered:
                            logger.error(
                                f"Path {worktree_path} is still registered as worktree, "
                                f"refusing to rmtree (would corrupt git state)"
                            )
                            # Don't return early - emit failure event first
                        else:
                            # Not registered - safe to remove directory
                            logger.info(
                                f"Path {worktree_path} not registered as worktree, "
                                f"safe to remove directory"
                            )
                            shutil.rmtree(worktree_path)
                            worktree_removed = True
            else:
                worktree_removed = True  # Already gone
                worktree_list_excerpt = None

            # If worktree is still registered, handle based on force flag
            if still_registered and not worktree_removed:
                failure_payload = {
                    "worktree_path": str(worktree_path),
                    "worktree_removed": False,
                    "cleanup_failed": True,
                    "failure_reason": "Worktree still registered, cannot safely remove",
                    "git_worktree_remove_stderr": _sanitize_output(worktree_remove_error),
                    "git_worktree_list_excerpt": _sanitize_output(worktree_list_excerpt),
                    "branch_name": workspace.branch_name,
                    "branch_was_merged": branch_merged,
                    "force_used": force,
                    "still_registered": True,
                }

                if not force:
                    # Not forcing - emit failure event and return
                    event = TicketEvent(
                        ticket_id=ticket_id,
                        event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                        from_state=None,
                        to_state=None,
                        actor_type=ActorType.SYSTEM.value,
                        actor_id=actor_id,
                        reason=f"Worktree cleanup FAILED: {worktree_path} (still registered)",
                        payload_json=json.dumps(failure_payload),
                    )
                    self.db.add(event)
                    await self.db.flush()
                    return False
                else:
                    # force=True but still registered = FAILURE state
                    # We emit a failure event and return False (don't set cleaned_up_at)
                    # This keeps DB state honest: cleanup did not actually succeed
                    logger.warning(
                        f"Force=True but worktree {worktree_path} still registered. "
                        f"Cannot safely proceed - returning failure."
                    )
                    event = TicketEvent(
                        ticket_id=ticket_id,
                        event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                        from_state=None,
                        to_state=None,
                        actor_type=ActorType.SYSTEM.value,
                        actor_id=actor_id,
                        reason=f"Worktree cleanup FAILED: {worktree_path} still registered (force=True cannot override)",
                        payload_json=json.dumps(failure_payload),
                    )
                    self.db.add(event)
                    await self.db.flush()
                    # Return False - cleanup did NOT succeed
                    # workspace.cleaned_up_at remains NULL
                    return False

            # =====================================================================
            # STEP 3: Prune stale worktree entries
            # =====================================================================
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=repo_path,
                capture_output=True,
                timeout=30,
            )

            # =====================================================================
            # STEP 4: Delete branch (decision was made in Step 1)
            # Branch deletion failure is NON-FATAL - cleanup continues
            # =====================================================================
            branch_deleted = False
            branch_delete_error = None

            if should_delete_branch:
                # Use -D for force, -d for safe (safe -d can fail if not merged, that's ok)
                delete_flag = "-D" if delete_branch else "-d"
                result = subprocess.run(
                    ["git", "branch", delete_flag, workspace.branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                branch_deleted = result.returncode == 0
                if not branch_deleted:
                    branch_delete_error = result.stderr.strip()
                    # This is NON-FATAL - log but don't fail cleanup
                    logger.warning(
                        f"Branch deletion failed (non-fatal): {workspace.branch_name}: "
                        f"{branch_delete_error}"
                    )

            # =====================================================================
            # STEP 5: Build cleanup event payload (always - for observability)
            # =====================================================================
            payload = {
                "worktree_path": str(worktree_path),
                "worktree_removed": worktree_removed,
                "branch_name": workspace.branch_name,
                # Distinguish between skip vs failure:
                # - branch_delete_attempted: True if we tried to delete, False if skipped
                # - branch_deleted: True only if deletion succeeded
                # - branch_delete_error: Set only if attempted and failed
                "branch_delete_attempted": should_delete_branch,
                "branch_deleted": branch_deleted,
                "branch_was_merged": branch_merged,
            }
            if branch_skip_reason:
                payload["branch_skip_reason"] = branch_skip_reason
            if branch_delete_error:
                payload["branch_delete_error"] = _sanitize_output(branch_delete_error)
            if git_verification_reason and not should_delete_branch:
                payload["git_verification_failed"] = git_verification_reason
            if used_base_branch:
                payload["base_branch_used"] = used_base_branch

            # =====================================================================
            # STEP 6: Only mark cleanup successful if worktree was actually removed
            # =====================================================================
            if not worktree_removed:
                # Worktree not removed - emit failure event and return False
                logger.error(
                    f"Cleanup FAILED for {worktree_path}: worktree was not removed"
                )
                payload["cleanup_failed"] = True
                payload["failure_reason"] = "Worktree was not removed"

                event = TicketEvent(
                    ticket_id=ticket_id,
                    event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                    from_state=None,
                    to_state=None,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=actor_id,
                    reason=f"Worktree cleanup FAILED: {worktree_path}",
                    payload_json=json.dumps(payload),
                )
                self.db.add(event)
                await self.db.flush()
                # Do NOT set cleaned_up_at - cleanup didn't succeed
                return False

            # Worktree was removed - mark as cleaned up
            workspace.cleaned_up_at = datetime.now(UTC)
            await self.db.flush()

            event = TicketEvent(
                ticket_id=ticket_id,
                event_type=EventType.WORKTREE_CLEANED.value,
                from_state=None,
                to_state=None,
                actor_type=ActorType.SYSTEM.value,
                actor_id=actor_id,
                reason=f"Worktree cleaned up: {worktree_path}",
                payload_json=json.dumps(payload),
            )
            self.db.add(event)
            await self.db.flush()

            logger.info(f"Deleted worktree {worktree_path} for ticket {ticket_id}")
            return True

        except Exception as e:
            logger.exception(f"Failed to delete worktree {worktree_path}: {e}")
            # Emit failure audit event for exception
            try:
                event = TicketEvent(
                    ticket_id=ticket_id,
                    event_type=EventType.WORKTREE_CLEANUP_FAILED.value,
                    from_state=None,
                    to_state=None,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=actor_id,
                    reason=f"Worktree cleanup EXCEPTION: {worktree_path}",
                    payload_json=json.dumps({
                        "worktree_path": str(worktree_path),
                        "cleanup_failed": True,
                        "failure_reason": f"Exception: {_sanitize_output(str(e))}",
                        "exception_type": type(e).__name__,
                        "branch_name": workspace.branch_name,
                    }),
                )
                self.db.add(event)
                await self.db.flush()
            except Exception as event_error:
                # Don't let event emission failure mask the original error
                logger.error(f"Failed to emit cleanup failure event: {event_error}")
            return False

    async def cleanup_stale_worktrees(
        self,
        dry_run: bool = True,
    ) -> CleanupResult:
        """Clean up stale worktrees that exceed TTL.

        Only cleans worktrees for tickets in DONE or ABANDONED state,
        or BLOCKED tickets older than TTL.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            CleanupResult with counts and details
        """
        result = CleanupResult()
        cleanup_config = self.config_service.get_cleanup_config()

        ttl_threshold = datetime.now(UTC) - timedelta(days=cleanup_config.worktree_ttl_days)

        # Find stale workspaces with their tickets
        query = (
            select(Workspace)
            .where(
                Workspace.cleaned_up_at.is_(None),
                Workspace.created_at < ttl_threshold,
            )
            .options(selectinload(Workspace.ticket))
        )
        stale_result = await self.db.execute(query)
        stale_workspaces = list(stale_result.scalars().all())

        for workspace in stale_workspaces:
            ticket = workspace.ticket
            worktree_path = Path(workspace.worktree_path)

            # Check ticket state - only clean if in safe state
            if ticket and ticket.state in PROTECTED_TICKET_STATES:
                result.details.append(
                    f"[SKIPPED] Worktree {worktree_path} - ticket in {ticket.state} state"
                )
                result.worktrees_skipped += 1
                continue

            # Safe to delete: done, abandoned, or blocked older than TTL
            result.details.append(
                f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
                f"stale worktree: {worktree_path} (created {workspace.created_at})"
            )

            if not dry_run:
                success = await self.delete_worktree(
                    workspace=workspace,
                    ticket_id=workspace.ticket_id,
                    actor_id="cleanup_stale_worktrees",
                    force=True,  # We already checked state above
                )
                if success:
                    result.worktrees_deleted += 1
                else:
                    result.worktrees_failed += 1
            else:
                result.worktrees_deleted += 1  # Count as would-be-deleted for dry run

        return result

    async def cleanup_orphaned_worktrees(
        self,
        dry_run: bool = True,
    ) -> CleanupResult:
        """Clean up orphaned worktree directories not tracked in database.

        Uses `git worktree remove` for directories that are git worktrees,
        and falls back to directory removal for non-git directories.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            CleanupResult with counts and details
        """
        result = CleanupResult()
        repo_path = self.config_service.get_repo_root()
        worktrees_dir = repo_path / self.WORKTREES_DIR

        if not worktrees_dir.exists():
            return result

        # Get all tracked worktree paths
        query = select(Workspace.worktree_path)
        tracked_result = await self.db.execute(query)
        tracked_paths = {Path(p).resolve() for p in tracked_result.scalars().all()}

        # Find orphaned directories
        for entry in worktrees_dir.iterdir():
            if not entry.is_dir():
                continue

            if entry.resolve() in tracked_paths:
                continue

            size = self._get_dir_size(entry)
            result.details.append(
                f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
                f"orphaned worktree: {entry} ({size // 1024}KB)"
            )

            if not dry_run:
                try:
                    # Try git worktree remove first
                    git_result = subprocess.run(
                        ["git", "worktree", "remove", "--force", str(entry)],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    if git_result.returncode != 0:
                        # Fallback to manual removal if git command fails
                        shutil.rmtree(entry)

                    # Always prune after removal
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=30,
                    )

                    result.worktrees_deleted += 1
                    result.bytes_freed += size
                except Exception as e:
                    logger.error(f"Failed to delete orphaned worktree {entry}: {e}")
                    result.worktrees_failed += 1
            else:
                result.worktrees_deleted += 1
                result.bytes_freed += size

        return result

    async def cleanup_old_evidence(
        self,
        dry_run: bool = True,
    ) -> CleanupResult:
        """Clean up evidence files older than TTL.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            CleanupResult with counts and details
        """
        result = CleanupResult()
        cleanup_config = self.config_service.get_cleanup_config()
        repo_path = self.config_service.get_repo_root()

        ttl_threshold = datetime.now(UTC) - timedelta(days=cleanup_config.evidence_ttl_days)

        # Find old evidence records
        query = select(Evidence).where(Evidence.created_at < ttl_threshold)
        old_result = await self.db.execute(query)
        old_evidence = list(old_result.scalars().all())

        for evidence in old_evidence:
            # Delete stdout file
            if evidence.stdout_path:
                stdout_path = repo_path / evidence.stdout_path
                if self._is_safe_path(stdout_path, repo_path):
                    size = stdout_path.stat().st_size if stdout_path.exists() else 0
                    result.details.append(
                        f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
                        f"evidence file: {stdout_path} ({size // 1024}KB)"
                    )

                    if not dry_run and stdout_path.exists():
                        try:
                            stdout_path.unlink()
                            result.evidence_files_deleted += 1
                            result.bytes_freed += size
                        except Exception as e:
                            logger.error(f"Failed to delete evidence file {stdout_path}: {e}")
                            result.evidence_files_failed += 1

            # Delete stderr file
            if evidence.stderr_path:
                stderr_path = repo_path / evidence.stderr_path
                if self._is_safe_path(stderr_path, repo_path):
                    size = stderr_path.stat().st_size if stderr_path.exists() else 0
                    result.details.append(
                        f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} "
                        f"evidence file: {stderr_path}"
                    )

                    if not dry_run and stderr_path.exists():
                        try:
                            stderr_path.unlink()
                            result.evidence_files_deleted += 1
                            result.bytes_freed += size
                        except Exception as e:
                            logger.error(f"Failed to delete evidence file {stderr_path}: {e}")
                            result.evidence_files_failed += 1

        return result

    async def run_full_cleanup(
        self,
        dry_run: bool = True,
        delete_worktrees: bool = True,
        delete_evidence: bool = True,
    ) -> CleanupResult:
        """Run full cleanup of worktrees and evidence.

        Args:
            dry_run: If True, only report what would be deleted
            delete_worktrees: Whether to delete stale worktrees
            delete_evidence: Whether to delete old evidence

        Returns:
            Combined CleanupResult
        """
        combined = CleanupResult()

        if delete_worktrees:
            # Cleanup stale worktrees
            stale_result = await self.cleanup_stale_worktrees(dry_run=dry_run)
            combined.worktrees_deleted += stale_result.worktrees_deleted
            combined.worktrees_failed += stale_result.worktrees_failed
            combined.worktrees_skipped += stale_result.worktrees_skipped
            combined.bytes_freed += stale_result.bytes_freed
            combined.details.extend(stale_result.details)

            # Cleanup orphaned worktrees
            orphan_result = await self.cleanup_orphaned_worktrees(dry_run=dry_run)
            combined.worktrees_deleted += orphan_result.worktrees_deleted
            combined.worktrees_failed += orphan_result.worktrees_failed
            combined.bytes_freed += orphan_result.bytes_freed
            combined.details.extend(orphan_result.details)

        if delete_evidence:
            evidence_result = await self.cleanup_old_evidence(dry_run=dry_run)
            combined.evidence_files_deleted += evidence_result.evidence_files_deleted
            combined.evidence_files_failed += evidence_result.evidence_files_failed
            combined.bytes_freed += evidence_result.bytes_freed
            combined.details.extend(evidence_result.details)

        if not dry_run:
            await self.db.commit()

        return combined

    def _is_safe_path(self, path: Path, repo_root: Path) -> bool:
        """Check if a path is safe to delete (under .smartkanban/).

        Args:
            path: Path to check
            repo_root: Repository root path

        Returns:
            True if path is safe to delete
        """
        try:
            resolved = path.resolve()
            smartkanban_root = (repo_root / self.SMARTKANBAN_DIR).resolve()
            common = os.path.commonpath([str(resolved), str(smartkanban_root)])
            return common == str(smartkanban_root)
        except (ValueError, OSError):
            return False

    def _get_dir_size(self, path: Path) -> int:
        """Get total size of a directory in bytes.

        Args:
            path: Directory path

        Returns:
            Total size in bytes
        """
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception:
            pass
        return total
